package eu.cormerais.stopclop;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import java.time.ZonedDateTime;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.json.JSONObject;

/** Optional, best-effort daily/weekly reminders using the account timezone. */
public final class ReminderJobService extends JobService {
    private static final int JOB=7045;
    private static final String CHANNEL="coaching-reminders";
    private final ExecutorService worker=Executors.newSingleThreadExecutor();private Future<?> work;
    private static SharedPreferences state(Context c){return c.getSharedPreferences("coaching-reminders",Context.MODE_PRIVATE);}
    static void configure(Context c,JSONObject settings){
        JSONObject prefs=settings.optJSONObject("reminders");if(prefs==null)return;
        String scope=CounterWidget.currentScope(c);SharedPreferences stored=state(c);
        if(!scope.equals(stored.getString("scope","")))stored.edit().clear().putString("scope",scope).commit();
        boolean enabled=prefs.optBoolean("daily_enabled")||prefs.optBoolean("weekly_enabled");stored.edit().putBoolean("enabled",enabled).apply();
        if(!enabled||scope.isEmpty()){cancel(c);return;}schedule(c);
    }
    private static void schedule(Context c){
        JobScheduler scheduler=c.getSystemService(JobScheduler.class);
        if(scheduler.getPendingJob(JOB)==null)scheduler.schedule(new JobInfo.Builder(JOB,new ComponentName(c,ReminderJobService.class))
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).setPeriodic(15*60*1000).setPersisted(true).build());
    }
    static void restore(Context c){if(state(c).getBoolean("enabled",false)&&!CounterWidget.currentScope(c).isEmpty())schedule(c);}
    static void cancel(Context c){c.getSystemService(JobScheduler.class).cancel(JOB);NotificationManager n=c.getSystemService(NotificationManager.class);n.cancel(7046);n.cancel(7047);}
    @Override public boolean onStartJob(JobParameters params){
        work=worker.submit(()->{try{
            String scope=CounterWidget.currentScope(this);if(scope.isEmpty())return;
            JSONObject settings=(JSONObject)ApiClient.request(CounterWidget.server(this),TokenStore.load(this),CounterWidget.language(this),"/settings","GET",null,null);
            if(Thread.currentThread().isInterrupted()||!scope.equals(CounterWidget.currentScope(this)))return;
            configure(this,settings);JSONObject prefs=settings.optJSONObject("reminders");if(prefs==null)return;
            NotificationManager manager=getSystemService(NotificationManager.class);if(!manager.areNotificationsEnabled())return;
            Translations t=new Translations(this,settings.getString("language"));
            manager.createNotificationChannel(new NotificationChannel(CHANNEL,t.text("reminders_title"),NotificationManager.IMPORTANCE_DEFAULT));
            ZonedDateTime current=ZonedDateTime.parse(settings.getString("local_datetime"));
            for(String kind:new String[]{"daily","weekly"}){
                String slot=ReminderPolicy.slot(current,prefs.optBoolean(kind+"_enabled"),prefs.getString(kind+"_time"),kind.equals("weekly")?prefs.getInt("weekly_day"):-1,prefs.getString("quiet_start"),prefs.getString("quiet_end"));
                if(slot.isEmpty()||slot.equals(state(this).getString(kind,"")))continue;
                if(!scope.equals(CounterWidget.currentScope(this))||Thread.currentThread().isInterrupted())return;
                Intent open=new Intent(this,CoachingActivity.class).setFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP);
                PendingIntent pending=PendingIntent.getActivity(this,7045,open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
                String message=t.text(kind+"_reminder_message");
                manager.notify(kind.equals("daily")?7046:7047,new Notification.Builder(this,CHANNEL).setSmallIcon(R.drawable.ic_notification)
                    .setContentTitle(t.text("journey_title")).setContentText(message).setStyle(new Notification.BigTextStyle().bigText(message))
                    .setContentIntent(pending).setAutoCancel(true).setOnlyAlertOnce(true).setVisibility(Notification.VISIBILITY_PRIVATE).build());
                state(this).edit().putString(kind,slot).commit();
            }
        }catch(ApiClient.HttpError e){if(e.status==401)TokenStore.clear(this);}catch(Exception ignored){}
        finally{if(!Thread.currentThread().isInterrupted())jobFinished(params,false);}});return true;
    }
    @Override public boolean onStopJob(JobParameters params){if(work!=null)work.cancel(true);return true;}
    @Override public void onDestroy(){worker.shutdownNow();super.onDestroy();}
}
