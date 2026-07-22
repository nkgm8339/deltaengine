// HFMQuoteObserver.mq5 -- quote observation only. It never sends an order.
#property strict
#property version   "1.00"
#property description "Writes the attached HFM chart's Bid/Ask to the MT5 common folder."

input string QuoteFileName = "DeltaEngine_HFM_quotes_utf8.jsonl";

int  QuoteFileHandle = INVALID_HANDLE;
long QuoteSequence   = 0;

bool OpenQuoteFile()
{
   QuoteFileHandle = FileOpen(
      QuoteFileName,
      FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_COMMON,
      '\n',
      CP_UTF8
   );
   if(QuoteFileHandle == INVALID_HANDLE)
   {
      Print("HFMQuoteObserver FileOpen failed: ", GetLastError());
      return false;
   }
   FileSeek(QuoteFileHandle, 0, SEEK_END);
   return true;
}

int OnInit()
{
   Print("HFMQuoteObserver is observation-only; symbol=", _Symbol);
   OpenQuoteFile();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(QuoteFileHandle != INVALID_HANDLE)
   {
      FileFlush(QuoteFileHandle);
      FileClose(QuoteFileHandle);
      QuoteFileHandle = INVALID_HANDLE;
   }
}

void OnTick()
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick) || tick.bid <= 0 || tick.ask < tick.bid)
      return;

   if(QuoteFileHandle == INVALID_HANDLE && !OpenQuoteFile())
      return;

   QuoteSequence++;

   string payload = StringFormat(
      "{\"symbol\":\"%s\",\"server_time_msc\":%I64d,\"sequence\":%I64d,\"bid\":%s,\"ask\":%s}\n",
      _Symbol,
      tick.time_msc,
      QuoteSequence,
      DoubleToString(tick.bid, _Digits),
      DoubleToString(tick.ask, _Digits)
   );
   ResetLastError();
   uint written = FileWriteString(QuoteFileHandle, payload);
   if(written == 0)
   {
      Print("HFMQuoteObserver FileWriteString failed: ", GetLastError());
      FileClose(QuoteFileHandle);
      QuoteFileHandle = INVALID_HANDLE;
      return;
   }
   FileFlush(QuoteFileHandle);
}
