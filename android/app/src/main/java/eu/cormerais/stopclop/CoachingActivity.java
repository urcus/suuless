package eu.cormerais.stopclop;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.DatePickerDialog;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.View;
import android.widget.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.time.*;
import java.util.*;
import java.text.NumberFormat;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Native companion to the user-owned coaching API. No personal data leaves the chosen server. */
public final class CoachingActivity extends Activity {
    private final ExecutorService network=Executors.newSingleThreadExecutor();
    private final Handler handler=new Handler(Looper.getMainLooper());
    private LinearLayout content,body;private TextView status,clock;private boolean busy;private String phase="overview",language,server,token,checkinDay;
    private JSONObject data,settings;private Translations translations;private long clockOffset;
    private final String[] triggers={"","coffee","stress","meal","social","boredom","other"},strategies={"walk","water","breathe","distract"};
    interface Work{Object run() throws Exception;} interface Done{void accept(Object value) throws Exception;}
    private String t(String key,Object...args){return translations.text(key,args);}
    private String n(double value){return NumberFormat.getNumberInstance(Locale.forLanguageTag(language)).format(value);}
    private int dp(int value){return Ui.dp(this,value);}
    @Override public void onCreate(Bundle state){
        super.onCreate(state);server=CounterWidget.server(this);token=TokenStore.load(this);language=CounterWidget.language(this);translations=new Translations(this,language);
        if(token.isEmpty()){startActivity(new Intent(this,MainActivity.class).putExtra("open_coaching_craving",getIntent().getBooleanExtra("craving",false)));finish();return;}
        phase=getIntent().getBooleanExtra("craving",false)?"craving":"overview";screen(t("journey_title"));load();
    }
    @Override public void onResume(){super.onResume();handler.post(ticker);}
    @Override public void onPause(){handler.removeCallbacks(ticker);super.onPause();}
    @Override public void onRestart(){super.onRestart();if(!phase.equals("plan"))load();}
    @Override public void onDestroy(){handler.removeCallbacksAndMessages(null);network.shutdownNow();super.onDestroy();}
    @Override public void onBackPressed(){if(!busy&&!phase.equals("overview")){phase="overview";load();}else super.onBackPressed();}
    private final Runnable ticker=new Runnable(){public void run(){
        JSONObject craving=data==null?null:data.optJSONObject("pending_craving");
        if(clock!=null&&craving!=null){long seconds=Math.max(0,(Instant.parse(craving.optString("pause_until")).toEpochMilli()-System.currentTimeMillis()-clockOffset+999)/1000);
            clock.setText(seconds==0?t("pause_done"):t("pause_remaining",Long.toString(seconds/60),String.format(Locale.ROOT,"%02d",seconds%60)));}
        handler.postDelayed(this,1000);
    }};
    private void screen(String title){
        clock=null;LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(Ui.PAPER);
        root.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());return insets;});
        LinearLayout header=new LinearLayout(this);header.setPadding(dp(18),dp(8),dp(18),0);
        Button back=Ui.button(this,t("back"),false,()->{if(!busy)onBackPressed();});header.addView(back,new LinearLayout.LayoutParams(0,-2,1));
        Button refresh=Ui.button(this,t("refresh"),false,()->{if(!busy)load();});header.addView(refresh,new LinearLayout.LayoutParams(0,-2,1));root.addView(header);
        status=Ui.label(this,"",13,Ui.ORANGE,false);status.setPadding(dp(24),0,dp(24),0);status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);root.addView(status);
        ScrollView scroll=new ScrollView(this);content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);content.setPadding(dp(24),dp(16),dp(24),dp(24));scroll.addView(content);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));setContentView(root);root.requestApplyInsets();body=content;label(title,28);
    }
    private void section(){content=Ui.card(this,Ui.WHITE);body.addView(content);}
    private TextView label(String value,int size){TextView text=Ui.label(this,value,size,size>=18?Ui.INK:Ui.MUTED,size>=18);text.setPadding(0,dp(6),0,dp(8));content.addView(text);return text;}
    private Button button(String value,Runnable action){Button b=Ui.button(this,value,false,()->{if(!busy)action.run();});content.addView(b);return b;}
    private EditText input(String title,String value,int type){
        TextView caption=label(title,13);EditText field=new EditText(this);field.setId(View.generateViewId());caption.setLabelFor(field.getId());field.setSingleLine(true);field.setInputType(type);field.setText(value);field.setTextSize(16);field.setTextColor(Ui.INK);field.setPadding(dp(12),dp(12),dp(12),dp(12));field.setBackground(Ui.shape(this,Ui.WHITE,12));content.addView(field);return field;
    }
    private EditText dateInput(String key,String value){EditText field=input(t(key),value,InputType.TYPE_CLASS_DATETIME|InputType.TYPE_DATETIME_VARIATION_DATE);button(t("choose_datetime"),()->{
        LocalDate initial;try{initial=LocalDate.parse(field.getText().toString());}catch(Exception e){initial=LocalDate.parse(data.optString("local_today"));}
        new DatePickerDialog(this,(picker,y,m,d)->field.setText(LocalDate.of(y,m+1,d).toString()),initial.getYear(),initial.getMonthValue()-1,initial.getDayOfMonth()).show();});return field;}
    private Spinner picker(String key,String[] values,String[] labels,String selected){
        TextView caption=label(t(key),13);Spinner spinner=new Spinner(this);spinner.setId(View.generateViewId());caption.setLabelFor(spinner.getId());ArrayAdapter<String> adapter=new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,labels);spinner.setAdapter(adapter);spinner.setBackground(Ui.dropdown(this));spinner.setPadding(dp(12),dp(10),dp(28),dp(10));spinner.setSelection(Math.max(0,Arrays.asList(values).indexOf(selected)));content.addView(spinner);return spinner;
    }
    private String[] translated(String prefix,String[] codes){String[] result=new String[codes.length];for(int i=0;i<codes.length;i++){String key=prefix+(codes[i].isEmpty()?"none":codes[i]);result[i]=t(key);}return result;}
    private CheckBox check(String key,boolean checked){CheckBox box=new CheckBox(this);box.setText(t(key));box.setChecked(checked);content.addView(box);return box;}
    private String costs(JSONObject amounts){ArrayList<String> values=new ArrayList<>();ArrayList<String> codes=new ArrayList<>();amounts.keys().forEachRemaining(codes::add);Collections.sort(codes);for(String code:codes){NumberFormat format=NumberFormat.getNumberInstance(Locale.forLanguageTag(language));int digits=2;try{digits=Math.max(0,java.util.Currency.getInstance(code).getDefaultFractionDigits());}catch(Exception ignored){}format.setMinimumFractionDigits(digits);format.setMaximumFractionDigits(digits);values.add(code+" "+format.format(amounts.optDouble(code)));}return String.join(" · ",values);}
    private Object api(String path,String method,JSONObject payload,String key) throws Exception{return ApiClient.request(server,token,language,path,method,payload,key);}
    private void perform(Work work,Done done){if(busy)return;busy=true;status.setText(t("connecting"));network.execute(()->{try{Object result=work.run();runOnUiThread(()->{if(isDestroyed())return;busy=false;status.setText("");try{done.accept(result);}catch(Exception e){status.setText(e.getMessage());}});}catch(Exception e){runOnUiThread(()->{if(isDestroyed())return;busy=false;if(e instanceof ApiClient.HttpError&&((ApiClient.HttpError)e).status==401){TokenStore.clear(this);startActivity(new Intent(this,MainActivity.class));finish();return;}status.setText(e instanceof java.io.IOException?t("network_error"):e.getMessage());});}});}
    private void load(){perform(()->new JSONObject().put("settings",api("/settings","GET",null,null)).put("coaching",api("/coaching","GET",null,null)),result->{
        JSONObject value=(JSONObject)result;settings=value.getJSONObject("settings");language=settings.getString("language");translations=new Translations(this,language);data=value.getJSONObject("coaching");clockOffset=Instant.parse(data.getString("now")).toEpochMilli()-System.currentTimeMillis();ReminderJobService.configure(this,settings);
        if(phase.equals("craving"))craving();else if(phase.equals("plan"))editPlan();else overview();});}
    private void saveAction(String path,String method,JSONObject payload){perform(()->api(path,method,payload,null),value->load());}
    private void overview() throws Exception {
        phase="overview";screen(t("journey_title"));section();JSONObject plan=data.getJSONObject("plan");String modeKey="mode_"+plan.getString("mode");label(t(modeKey),19);if(!plan.getString("reason").isEmpty())label(plan.getString("reason"),16);
        JSONArray days=data.getJSONArray("days");if(!data.isNull("current_goal"))label(t("goal_today",n(data.getInt("current_goal")),n(days.getJSONObject(days.length()-1).getInt("quantity"))),15);
        button(t("journey_mode"),()->{phase="plan";try{editPlan();}catch(Exception e){status.setText(e.getMessage());}});
        button(t("craving_button"),()->{phase="craving";load();});
        section();label(t("progress_title"),22);label(t("smoke_free_total",n(data.getInt("confirmed_smoke_free_days"))),17);label(t("cravings_passed",n(data.getInt("cravings_passed"))),17);
        if(!data.isNull("quit_since")){long hours=Duration.between(Instant.parse(data.getString("quit_since")),Instant.parse(data.getString("now"))).toHours();label(t("quit_clock",n(Math.max(0,hours)/24),n(Math.max(0,hours)%24)),14);}label(t("setback_note"),13);
        section();label(t("checkin_title"),22);String[] dates=new String[days.length()];for(int i=0;i<dates.length;i++)dates[i]=days.getJSONObject(days.length()-1-i).getString("date");if(checkinDay==null)checkinDay=LocalDate.parse(data.getString("local_today")).minusDays(1).toString();
        Spinner selected=picker("day",dates,dates,checkinDay);TextView detail=label("",15);Button confirm=button(t("checkin_title"),()->{});Button reopen=button(t("unconfirm_day"),()->{});
        Runnable selection=()->{try{checkinDay=dates[selected.getSelectedItemPosition()];JSONObject day=days.getJSONObject(days.length()-1-selected.getSelectedItemPosition());boolean confirmed=day.getBoolean("confirmed");detail.setText(t(confirmed?"confirmed_day":"unconfirmed_day")+" · "+t("quantity_count",n(day.getInt("quantity"))));confirm.setText(t("confirm_day",n(day.getInt("quantity"))));confirm.setVisibility(confirmed?View.GONE:View.VISIBLE);reopen.setVisibility(confirmed?View.VISIBLE:View.GONE);
            confirm.setOnClickListener(v->{if(!busy)try{saveAction("/check-ins/"+checkinDay,"PUT",new JSONObject().put("quantity",day.getInt("quantity")));}catch(Exception e){status.setText(e.getMessage());}});reopen.setOnClickListener(v->{if(!busy)saveAction("/check-ins/"+checkinDay,"DELETE",null);});}catch(Exception e){status.setText(e.getMessage());}};
        selected.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onNothingSelected(AdapterView<?> p){}public void onItemSelected(AdapterView<?> p,View v,int i,long id){selection.run();}});selection.run();label(t("checkin_note"),13);
        section();label(t("baseline_title"),22);JSONObject baseline=plan.optJSONObject("baseline");
        if(baseline==null){LocalDate today=LocalDate.parse(data.getString("local_today"));EditText start=dateInput("from",today.minusDays(7).toString()),end=dateInput("until",today.minusDays(1).toString());label(t("baseline_note"),13);button(t("baseline_freeze"),()->{try{saveAction("/coaching/baseline","POST",new JSONObject().put("start",start.getText().toString()).put("end",end.getText().toString()));}catch(Exception e){status.setText(e.getMessage());}});}
        else label(t("baseline_summary",baseline.getString("start"),baseline.getString("end"),n(baseline.getDouble("quantity")/baseline.getInt("days")),baseline.getString("timezone")),14);
        JSONObject progress=data.optJSONObject("progress");if(progress==null||progress.getInt("confirmed_days")==0)label(t("progress_missing"),14);else {label(t(progress.getDouble("quantity_difference")<0?"progress_increase":"progress_value",n(Math.abs(progress.getDouble("quantity_difference"))),n(Math.abs(progress.getDouble("reduction_percent"))),n(progress.getInt("confirmed_days"))),17);label(costs(progress.getJSONObject("estimated_cost_difference")),20);}label(t("progress_money_note"),13);
        section();label(t("weekly_title"),22);JSONObject weekly=data.getJSONObject("weekly"),current=weekly.getJSONObject("current");label(weekly.getString("start")+" — "+weekly.getString("end"),13);label(t("weekly_value",n(current.getInt("quantity")),n(weekly.getJSONObject("previous").getInt("quantity")),n(current.getInt("confirmed_days"))),16);label(costs(current.getJSONObject("costs")),16);
        section();label(t("craving_triggers"),22);JSONArray summary=data.getJSONArray("triggers");boolean has=false;for(int i=0;i<summary.length();i++){JSONObject row=summary.getJSONObject(i);if(row.getInt("cigarettes")+row.getInt("cravings")==0)continue;has=true;String key="trigger_"+row.getString("trigger");label(t("trigger_summary",t(key),n(row.getInt("cigarettes")),n(row.getInt("cravings")),n(row.getInt("passed"))),14);}if(!has)label(t("no_entries"),14);
        section();label(t("support_title"),22);label(t("support_note"),13);String country=plan.getString("country");String url=country.equals("FR")?"https://www.tabac-info-service.fr/j-arrete-de-fumer/mes-outils-tabac-info-service":country.equals("GB")?"https://www.nhs.uk/better-health/quit-smoking/":country.equals("JP")?"https://kennet.mhlw.go.jp/information/information/tobacco-summaries/t-06":"https://www.who.int/health-topics/tobacco";
        button(country.equals("FR")?"Tabac info service":country.equals("GB")?"NHS · Better Health":country.equals("JP")?"厚生労働省 · e-ヘルスネット":"WHO · Tobacco cessation",()->startActivity(new Intent(Intent.ACTION_VIEW,android.net.Uri.parse(url))));
        button(t("progress_export"),()->startActivityForResult(new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("text/csv").putExtra(Intent.EXTRA_TITLE,"suuless-progress.csv"),86));label(t("report_note"),13);
    }
    private void editPlan() throws Exception {
        phase="plan";screen(t("journey_title"));JSONObject original=new JSONObject(data.getJSONObject("plan").toString());String[] modes={"observe","reduce","quit"};Spinner mode=picker("journey_mode",modes,translated("mode_",modes),original.getString("mode"));
        EditText reason=input(t("personal_reason"),original.getString("reason"),InputType.TYPE_CLASS_TEXT);reason.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(300)});
        EditText goal=input(t("daily_target"),original.getString("daily_goal"),InputType.TYPE_CLASS_NUMBER),quit=dateInput("quit_date",original.isNull("quit_date")?"":original.getString("quit_date"));
        label(t("plan_steps"),20);LinearLayout rows=new LinearLayout(this);rows.setOrientation(LinearLayout.VERTICAL);content.addView(rows);ArrayList<EditText[]> steps=new ArrayList<>();
        JSONArray existing=original.getJSONArray("steps");for(int i=0;i<existing.length();i++)stepRow(rows,steps,existing.getJSONObject(i).getString("date"),existing.getJSONObject(i).getString("goal"));
        button(t("add_step"),()->{if(steps.size()<30)stepRow(rows,steps,data.optString("local_today"),"0");});
        Spinner strategy=picker("craving_strategy",strategies,translated("strategy_",strategies),original.getString("strategy"));
        label(t("reminders_title"),20);CheckBox daily=check("daily_reminder",original.getBoolean("daily_enabled"));EditText dailyTime=input(t("reminder_time"),original.getString("daily_time"),InputType.TYPE_CLASS_DATETIME|InputType.TYPE_DATETIME_VARIATION_TIME);
        CheckBox weekly=check("weekly_reminder",original.getBoolean("weekly_enabled"));String[] weekdays={"0","1","2","3","4","5","6"},weekdayLabels=new String[7];for(int i=0;i<7;i++)weekdayLabels[i]=DayOfWeek.of(i+1).getDisplayName(java.time.format.TextStyle.FULL,Locale.forLanguageTag(language));Spinner weekday=picker("weekly_day",weekdays,weekdayLabels,original.getString("weekly_day"));
        EditText weeklyTime=input(t("reminder_time"),original.getString("weekly_time"),InputType.TYPE_CLASS_DATETIME|InputType.TYPE_DATETIME_VARIATION_TIME),quietStart=input(t("quiet_start"),original.getString("quiet_start"),InputType.TYPE_CLASS_DATETIME|InputType.TYPE_DATETIME_VARIATION_TIME),quietEnd=input(t("quiet_end"),original.getString("quiet_end"),InputType.TYPE_CLASS_DATETIME|InputType.TYPE_DATETIME_VARIATION_TIME);
        label(t("reminder_note"),13);button(t("reminder_permission"),()->{if(android.os.Build.VERSION.SDK_INT>=33&&checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS)!=android.content.pm.PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS},7045);else startActivity(new Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(android.provider.Settings.EXTRA_APP_PACKAGE,getPackageName()));});
        String[] countries={"other","FR","GB","JP"},countryLabels=new String[4];countryLabels[0]=t("support_other");for(int i=1;i<4;i++)countryLabels[i]=Locale.forLanguageTag("und-"+countries[i]).getDisplayCountry(Locale.forLanguageTag(language));Spinner country=picker("support_country",countries,countryLabels,original.getString("country"));
        button(t("save"),()->{try{
            JSONArray newSteps=new JSONArray();for(EditText[] step:steps)newSteps.put(new JSONObject().put("date",step[0].getText().toString()).put("goal",Integer.parseInt(step[1].getText().toString())));
            JSONObject values=new JSONObject().put("mode",modes[mode.getSelectedItemPosition()]).put("reason",reason.getText().toString()).put("daily_goal",Integer.parseInt(goal.getText().toString())).put("quit_date",quit.getText().toString().isEmpty()?JSONObject.NULL:quit.getText().toString()).put("steps",newSteps).put("strategy",strategies[strategy.getSelectedItemPosition()]).put("country",countries[country.getSelectedItemPosition()])
                .put("daily_enabled",daily.isChecked()).put("daily_time",dailyTime.getText().toString()).put("weekly_enabled",weekly.isChecked()).put("weekly_time",weeklyTime.getText().toString()).put("weekly_day",weekday.getSelectedItemPosition()).put("quiet_start",quietStart.getText().toString()).put("quiet_end",quietEnd.getText().toString());
            JSONObject changes=new JSONObject().put("version",original.getInt("version"));Iterator<String> keys=values.keys();while(keys.hasNext()){String key=keys.next();if(!values.get(key).toString().equals(original.get(key).toString()))changes.put(key,values.get(key));}
            perform(()->api("/coaching/plan","PUT",changes,null),saved->{Toast.makeText(this,t("plan_saved"),Toast.LENGTH_SHORT).show();phase="overview";load();});
        }catch(Exception e){status.setText(t("invalid_input"));}});
    }
    private void stepRow(LinearLayout parent,ArrayList<EditText[]> steps,String date,String goal){
        LinearLayout row=new LinearLayout(this);row.setOrientation(LinearLayout.VERTICAL);LinearLayout old=content;content=row;EditText d=dateInput("day",date),q=input(t("daily_target"),goal,InputType.TYPE_CLASS_NUMBER);EditText[] pair={d,q};steps.add(pair);button(t("delete"),()->{parent.removeView(row);steps.remove(pair);});content=old;parent.addView(row);
    }
    private void craving() throws Exception {
        phase="craving";screen(t("craving_button"));JSONObject current=data.optJSONObject("pending_craving");
        if(current==null){Spinner trigger=picker("craving_trigger",triggers,translated("trigger_",triggers),"");Spinner strategy=picker("craving_strategy",strategies,translated("strategy_",strategies),data.getJSONObject("plan").getString("strategy"));String[] minutes={"1","3","5","10"};Spinner duration=picker("pause_minutes",minutes,minutes,"3");
            button(t("start_pause"),()->{try{
                android.content.SharedPreferences pending=getSharedPreferences("coaching-pending",MODE_PRIVATE);String scope=CounterWidget.currentScope(this);if(!scope.equals(pending.getString("scope","")))pending.edit().clear().putString("scope",scope).commit();
                String key=pending.getString("key","");JSONObject payload;
                if(key.isEmpty()){key=UUID.randomUUID().toString();payload=new JSONObject().put("trigger",triggers[trigger.getSelectedItemPosition()]).put("strategy",strategies[strategy.getSelectedItemPosition()]).put("minutes",Integer.parseInt(minutes[duration.getSelectedItemPosition()]));pending.edit().putString("key",key).putString("payload",payload.toString()).commit();}
                else payload=new JSONObject(pending.getString("payload","{}"));final String requestKey=key;
                perform(()->api("/cravings","POST",payload,requestKey),result->{pending.edit().remove("key").remove("payload").commit();load();});
            }catch(Exception e){status.setText(t("invalid_input"));}});
        }else{
            String key="strategy_"+current.getString("strategy");label(t(key),20);clock=label("",28);
            for(String outcome:new String[]{"passed","smoked","cancelled"}){String labelKey="outcome_"+outcome;button(t(labelKey),()->{try{perform(()->api("/cravings/"+current.getInt("id"),"PUT",new JSONObject().put("outcome",outcome),null),result->{phase="overview";CounterWidget.enqueue(this,false);load();});}catch(Exception e){status.setText(e.getMessage());}});}
        }
    }
    @Override protected void onActivityResult(int requestCode,int resultCode,Intent result){super.onActivityResult(requestCode,resultCode,result);if(requestCode==86&&resultCode==RESULT_OK&&result!=null&&result.getData()!=null){android.net.Uri destination=result.getData();perform(()->{String report=(String)api("/coaching/export.csv","GET",null,null);try(java.io.OutputStream out=getContentResolver().openOutputStream(destination)){if(out==null)throw new java.io.IOException();out.write(report.getBytes(java.nio.charset.StandardCharsets.UTF_8));}return null;},value->Toast.makeText(this,t("entry_saved"),Toast.LENGTH_SHORT).show());}}
}
