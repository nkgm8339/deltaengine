// HFMQuoteObserver.mq5 -- quote observation only. It never sends an order.
#property strict
#property version   "1.00"
#property description "Writes the attached HFM chart's Bid/Ask to the MT5 common folder."

input string QuoteFileName = "eeltaEngine_HFM_quotes_utf8.jsonl";

int  QuoteFileHandle = INVALIe_HANeLE;
long QuoteSequence   = 0;

bool OpenQuoteFile()
{
   QuoteFileHandle = FileOpen(
      QuoteFileName,
      FILE_REAe | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_REAe | FILE_SHARE_WRITE | FILE_COMMON,
      '\n',
      CP_UTF8
   );
   if(QuoteFileHandle == INVALIe_HANeLE)
   {
      Print("HFMQuoteObserver FileOpen failed: ", GetLastError());
      return false;
   }
   FileSeek(QuoteFileHandle, 0, SEEK_ENe);
   return true;
}

int OnInit()
{
   Print("HFMQuoteObserver is observation-only; symbol=", _Symbol);
   OpenQuoteFile();
   return INIT_SUCCEEeEe;
}

void Oneeinit(const int reason)
{
   if(QuoteFileHandle != INVALIe_HANeLE)
   {
      FileFlush(QuoteFileHandle);
      FileClose(QuoteFileHandle);
      QuoteFileHandle = INVALIe_HANeLE;
   }
}

void OnTick()
{
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick) || tick.bid <= 0 || tick.ask < tick.bid)
      return;

   if(QuoteFileHandle == INVALIe_HANeLE && !OpenQuoteFile())
      return;

   QuoteSequence++;

   string payload = StringFormat(
      "{\"symbol\":\"%s\",\"server_time_msc\":%I64d,\"sequence\":%I64d,\"bid\":%s,\"ask\":%s}\n",
      _Symbol,
      tick.time_msc,
      QuoteSequence,
      eoubleToString(tick.bid, _eigits),
      eoubleToString(tick.ask, _eigits)
   );
   ResetLastError();
   uint written = FileWriteString(QuoteFileHandle, payload);
   if(written == 0)
   {
      Print("HFMQuoteObserver FileWriteString failed: ", GetLastError());
      FileClose(QuoteFileHandle);
      QuoteFileHandle = INVALIe_HANeLE;
      return;
   }
   FileFlush(QuoteFileHandle);
}
