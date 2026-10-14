package eu.cormerais.stopclop;

import android.app.PendingIntent;
import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.app.job.JobWorkItem;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.widget.RemoteViews;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.UUID;

/** One horizontal row, always scoped to the app's current encrypted session. */
public final class CounterWidget extends AppWidgetProvider {
    static final String ADD="eu.cormerais.stopclop.WIDGET_ADD",REFRESH="eu.cormerais.stopclop.WIDGET_REFRESH";
    static final int JOB_ID=7041;
    static SharedPreferences state(Context context){return context.getSharedPreferences("counter-widget",Context.MODE_PRIVATE);}
    static SharedPreferences preferences(Context context){return context.getSharedPreferences("MainActivity",Context.MODE_PRIVATE);}
    static String server(Context context){return preferences(context).getString("server","");}
    static String language(Context context){return preferences(context).getString("language","en");}
    static String scope(String server,String token){
        if(server.isEmpty()||token.isEmpty())return "";
        try{return android.util.Base64.encodeToString(MessageDigest.getInstance("SHA-256").digest((server+"\n"+token).getBytes(StandardCharsets.UTF_8)),android.util.Base64.NO_WRAP);}
        catch(Exception error){throw new IllegalStateException(error);}
    }
    static String currentScope(Context context){return scope(server(context),TokenStore.load(context));}
    private static synchronized String prepare(Context context){
        String scope=currentScope(context);SharedPreferences prefs=state(context);
        if(!scope.equals(prefs.getString("scope","")))prefs.edit().clear().putString("scope",scope).commit();
        return scope;
    }
    @Override public void onUpdate(Context context,AppWidgetManager manager,int[] ids){enqueue(context,false);}
    @Override public void onReceive(Context context,Intent intent){
        super.onReceive(context,intent);
        if(ADD.equals(intent.getAction()))enqueue(context,true);
        else if(REFRESH.equals(intent.getAction()))enqueue(context,false);
    }
    static synchronized void enqueue(Context context,boolean add){
        String scope=prepare(context);SharedPreferences prefs=state(context);
        if(scope.isEmpty()){render(context);return;}
        if(add&&prefs.getLong("busy_until",0)>System.currentTimeMillis())return;
        if(add&&prefs.getString("pending_key","").isEmpty())prefs.edit()
            .putString("pending_key",UUID.randomUUID().toString()).putString("pending_time",Instant.now().toString()).commit();
        if(add)prefs.edit().putLong("busy_until",System.currentTimeMillis()+60000).putString("error","").commit();
        JobInfo job=new JobInfo.Builder(JOB_ID,new ComponentName(context,WidgetJobService.class)).setOverrideDeadline(0).build();
        Intent work=new Intent().putExtra("scope",scope).putExtra("add",add);
        int result=context.getSystemService(JobScheduler.class).enqueue(job,new JobWorkItem(work));
        if(result!=JobScheduler.RESULT_SUCCESS)prefs.edit().putLong("busy_until",0).putString("error","widget_offline").commit();
        render(context);
    }
    static synchronized void acceptStats(Context context,String server,String token,JSONObject stats) throws Exception {
        String expected=scope(server,token);
        if(expected.isEmpty()||!expected.equals(currentScope(context)))return;
        prepare(context);
        state(context).edit().putInt("count",stats.getJSONObject("today").getInt("quantity"))
            .putString("day",stats.getString("end")).putString("zone",stats.getString("timezone"))
            .putLong("checked_at",System.currentTimeMillis()).putString("error","").commit();
        render(context);
    }
    static void render(Context context){
        String scope=prepare(context);SharedPreferences prefs=state(context);
        Translations t=new Translations(context,language(context));
        AppWidgetManager manager=AppWidgetManager.getInstance(context);
        int[] ids=manager.getAppWidgetIds(new ComponentName(context,CounterWidget.class));
        boolean busy=prefs.getLong("busy_until",0)>System.currentTimeMillis(),pending=!prefs.getString("pending_key","").isEmpty();
        String count="—";
        try{if(LocalDate.now(ZoneId.of(prefs.getString("zone","UTC"))).toString().equals(prefs.getString("day","")))
            count=java.text.NumberFormat.getIntegerInstance(Locale.forLanguageTag(language(context))).format(prefs.getInt("count",0));}
        catch(Exception ignored){}
        String note=t.text("widget_sign_in");
        if(!scope.isEmpty()){
            String error=prefs.getString("error","");
            if(busy)note=t.text("widget_pending");
            else if(!error.isEmpty())note=t.text(error);
            else if(prefs.getLong("checked_at",0)>0)note=t.text("widget_updated",DateTimeFormatter.ofPattern("HH:mm").withZone(ZoneId.systemDefault()).format(Instant.ofEpochMilli(prefs.getLong("checked_at",0))));
            else note=t.text("widget_refresh");
        }
        for(int id:ids){
            RemoteViews view=new RemoteViews(context.getPackageName(),R.layout.counter_widget);
            view.setTextViewText(R.id.widget_count,(scope.isEmpty()?t.text("app_name"):t.text("widget_today",count))+"\n"+note);
            view.setTextViewText(R.id.widget_plus,pending&&!busy?t.text("widget_retry"):"+1");
            view.setBoolean(R.id.widget_plus,"setEnabled",!scope.isEmpty()&&!busy);
            view.setContentDescription(R.id.widget_plus,t.text(pending?"widget_retry":"widget_add"));
            view.setContentDescription(R.id.widget_count,(scope.isEmpty()?t.text("widget_sign_in"):t.text("widget_today",count))+". "+t.text("widget_refresh")+". "+note);
            PendingIntent open=PendingIntent.getActivity(context,id,new Intent(context,MainActivity.class),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
            view.setTextViewText(R.id.widget_craving,t.text("craving_button"));view.setContentDescription(R.id.widget_craving,t.text("craving_button"));
            Intent urge=new Intent(context,MainActivity.class).setAction("eu.cormerais.stopclop.CRAVING").putExtra("open_coaching_craving",true).setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP);
            view.setOnClickPendingIntent(R.id.widget_craving,PendingIntent.getActivity(context,id,urge,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE));
            view.setOnClickPendingIntent(R.id.widget_open,open);
            view.setOnClickPendingIntent(R.id.widget_count,scope.isEmpty()?open:click(context,id,REFRESH));
            view.setOnClickPendingIntent(R.id.widget_plus,click(context,id,ADD));
            manager.updateAppWidget(id,view);
        }
    }
    private static PendingIntent click(Context context,int id,String action){return PendingIntent.getBroadcast(context,id,new Intent(context,CounterWidget.class).setAction(action),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);}
}
