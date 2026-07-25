// HFMSafeTestExecutor.mq5 -- constrained test executor.
// It is SHADOW-only by default.  Live orders require two explicit inputs.
#property strict
#property version   "1.00"
#property description "0.01-lot, one-position, SL-required HFM test executor with emergency-stop file."

#include <Trade/Trade.mqh>

input bool   EnableLiveOrders = false;
input string LiveConfirmation = "";
input double TestVolume       = 0.01;
input ulong  MagicNumber      = 26072501;
input int    MaxSpreadPoints  = 0;      // 0 = no spread gate; set explicitly before live use.
input string CommandFileName  = "DeltaEngine_HFM_order_command.txt";
input string EmergencyStopFileName = "DeltaEngine_HFM_EMERGENCY_STOP.flag";
input string AuditFileName    = "DeltaEngine_HFM_execution_audit.jsonl";

CTrade trade;
string last_command_id = "";

bool FileExistsCommon(const string name)
{
   int handle = FileOpen(name, FILE_READ | FILE_TXT | FILE_COMMON, '\n', CP_UTF8);
   if(handle == INVALID_HANDLE)
      return false;
   FileClose(handle);
   return true;
}

void Audit(const string command_id, const string status, const string detail)
{
   int handle = FileOpen(AuditFileName, FILE_READ | FILE_WRITE | FILE_TXT |
                         FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE |
                         FILE_COMMON, '\n', CP_UTF8);
   if(handle == INVALID_HANDLE)
   {
      Print("Audit FileOpen failed: ", GetLastError());
      return;
   }
   FileSeek(handle, 0, SEEK_END);
   string payload = StringFormat(
      "{\"server_time_msc\":%I64d,\"symbol\":\"%s\",\"command_id\":\"%s\",\"status\":\"%s\",\"detail\":\"%s\"}\n",
      (long)TimeCurrent() * 1000, _Symbol, command_id, status, detail
   );
   FileWriteString(handle, payload);
   FileFlush(handle);
   FileClose(handle);
}

bool HasManagedPosition()
{
   for(int index = PositionsTotal() - 1; index >= 0; index--)
   {
      ulong ticket = PositionGetTicket(index);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         (ulong)PositionGetInteger(POSITION_MAGIC) == MagicNumber)
         return true;
   }
   return false;
}

void EmergencyClose()
{
   for(int index = PositionsTotal() - 1; index >= 0; index--)
   {
      ulong ticket = PositionGetTicket(index);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol ||
         (ulong)PositionGetInteger(POSITION_MAGIC) != MagicNumber)
         continue;
      if(!trade.PositionClose(ticket))
         Print("Emergency close failed ticket=", ticket, " error=", GetLastError());
      else
         Audit("EMERGENCY", "CLOSED", "manual stop flag");
   }
}

bool ParseCommand(string &command_id, string &side, double &sl, double &tp)
{
   int handle = FileOpen(CommandFileName, FILE_READ | FILE_TXT | FILE_COMMON, '\n', CP_UTF8);
   if(handle == INVALID_HANDLE)
      return false;

   string line = "";
   string last = "";
   while(!FileIsEnding(handle))
   {
      line = FileReadString(handle);
      if(StringLen(line) > 0)
         last = line;
   }
   FileClose(handle);
   if(StringLen(last) == 0)
      return false;

   string fields[];
   int count = StringSplit(last, '|', fields);
   if(count != 4)
      return false;
   command_id = fields[0];
   side = fields[1];
   sl = StringToDouble(fields[2]);
   tp = StringToDouble(fields[3]);
   return StringLen(command_id) > 0 && (side == "BUY" || side == "SELL") && sl > 0;
}

void ProcessCommand()
{
   if(FileExistsCommon(EmergencyStopFileName))
   {
      EmergencyClose();
      return;
   }

   string command_id, side;
   double sl, tp;
   if(!ParseCommand(command_id, side, sl, tp) || command_id == last_command_id)
      return;
   last_command_id = command_id;

   if(HasManagedPosition())
   {
      Audit(command_id, "REJECTED", "managed position already exists");
      return;
   }

   double broker_min = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double broker_step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(TestVolume != 0.01 || broker_min > TestVolume || broker_step <= 0)
   {
      Audit(command_id, "REJECTED", "volume safety check failed");
      return;
   }

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick) || tick.bid <= 0 || tick.ask <= tick.bid)
   {
      Audit(command_id, "REJECTED", "invalid quote");
      return;
   }
   int spread = (int)MathRound((tick.ask - tick.bid) / _Point);
   if(MaxSpreadPoints > 0 && spread > MaxSpreadPoints)
   {
      Audit(command_id, "REJECTED", "spread gate");
      return;
   }

   double entry = side == "BUY" ? tick.ask : tick.bid;
   if((side == "BUY" && sl >= entry) || (side == "SELL" && sl <= entry))
   {
      Audit(command_id, "REJECTED", "stop loss is on unsafe side");
      return;
   }

   if(!EnableLiveOrders || LiveConfirmation != "I_UNDERSTAND_LIVE_01_LOT")
   {
      Audit(command_id, "SHADOW", "live order disabled");
      return;
   }

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(20);
   bool sent = side == "BUY"
      ? trade.Buy(TestVolume, _Symbol, 0.0, sl, tp, command_id)
      : trade.Sell(TestVolume, _Symbol, 0.0, sl, tp, command_id);
   Audit(command_id, sent ? "SENT" : "REJECTED", sent ? "order sent" : "broker rejected");
}

int OnInit()
{
   EventSetTimer(1);
   Print("HFMSafeTestExecutor started in ", EnableLiveOrders ? "LIVE-GATED" : "SHADOW", " mode on ", _Symbol);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   ProcessCommand();
}
