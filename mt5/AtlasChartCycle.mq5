#property service
#property version "1.00"
#property description "Atlas display-only D1 H4 H1 M15 M5 cycle. No trading functions."
input string DisplaySymbol="XAUUSD";
input int ScanIntervalSeconds=300;
input int DwellSeconds=5;
long managed=-1;
int lock_handle=INVALID_HANDLE;
string confirmed_sequence="";
string status_file="AtlasChartCycle_status.json";
ENUM_TIMEFRAMES frames[5]={PERIOD_D1,PERIOD_H4,PERIOD_H1,PERIOD_M15,PERIOD_M5};

string Label(ENUM_TIMEFRAMES tf){return StringSubstr(EnumToString(tf),7);}
void PositionLatest()
{
 ChartSetInteger(managed,CHART_AUTOSCROLL,true);
 ChartNavigate(managed,CHART_END,0);
 ChartRedraw(managed);
}
void Status(string state,int phase,string reason="")
{
 int h=FileOpen(status_file,FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ);
 if(h==INVALID_HANDLE)return;
 string tf=managed>=0?Label(ChartPeriod(managed)):"unknown";
 string text=StringFormat("{\"state\":\"%s\",\"symbol\":\"%s\",\"chart_id\":%I64d,\"actual_timeframe\":\"%s\",\"phase\":%d,\"checked_at_epoch_utc\":%I64d,\"reason\":\"%s\",\"display_only\":true,\"broker_authority\":false}",state,DisplaySymbol,managed,tf,phase,(long)TimeGMT(),reason);
 StringReplace(text,"\"display_only\":true", "\"confirmed_sequence\":\""+confirmed_sequence+"\",\"display_only\":true");
 FileWriteString(h,text);FileClose(h);
}
bool Valid(){return managed>=0 && ChartSymbol(managed)==DisplaySymbol && StringLen(ChartGetString(managed,CHART_EXPERT_NAME))==0;}
bool Switch(ENUM_TIMEFRAMES tf)
{
 if(!Valid())return false;
 if(ChartPeriod(managed)==tf){PositionLatest();return true;}
 if(!ChartSetSymbolPeriod(managed,DisplaySymbol,tf))return false;
 for(int n=0;n<50 && !IsStopped();n++)
 {
  if(!Valid())return false;
  if(ChartPeriod(managed)==tf){PositionLatest();return true;}
  Sleep(100);
 }
 return false;
}
void OnStart()
{
 if(DisplaySymbol!="XAUUSD" || ScanIntervalSeconds<60 || DwellSeconds<3 || DwellSeconds>15)return;
 lock_handle=FileOpen("AtlasChartCycle.lock",FILE_READ|FILE_WRITE|FILE_BIN|FILE_COMMON);
 if(lock_handle==INVALID_HANDLE){Print("Atlas chart cycle already running or lock unavailable");return;}
 int count=0;
 for(long c=ChartFirst();c>=0;c=ChartNext(c))
  if(ChartSymbol(c)==DisplaySymbol){managed=c;count++;}
 if(count!=1 || !Valid())
 {
  Status("blocked",-1,StringFormat("matching_charts_%d_expert_%s",count,ChartGetString(managed,CHART_EXPERT_NAME)));FileClose(lock_handle);return;
 }
 while(!IsStopped())
 {
  ulong started=GetTickCount64();bool ok=true;confirmed_sequence="";
  for(int phase=0;phase<5 && !IsStopped();phase++)
  {
   if(!Switch(frames[phase])){ok=false;break;}
   confirmed_sequence+=(phase>0?",":"")+Label(frames[phase]);
   Print("Atlas display confirmed ",Label(frames[phase]));
   Status("scanning",phase);
   for(int n=0;n<DwellSeconds && !IsStopped();n++)Sleep(1000);
  }
  if(!ok){Status("blocked",-1,"chart_switch_or_identity_failed");break;}
  Status("resting_on_M5",4);
  while(!IsStopped() && GetTickCount64()-started<(ulong)ScanIntervalSeconds*1000)
  {
   if(!Valid()){ok=false;break;}
   Status("resting_on_M5",4);Sleep(1000);
  }
  if(!ok){Status("blocked",-1,"chart_identity_changed");break;}
 }
 if(Valid())ChartSetSymbolPeriod(managed,DisplaySymbol,PERIOD_M5);
 Status("stopped",-1);FileClose(lock_handle);
}
