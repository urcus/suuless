package eu.cormerais.stopclop;

import android.app.job.JobParameters;
import android.app.job.JobService;
import android.app.job.JobWorkItem;
import android.content.SharedPreferences;
import org.json.JSONObject;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

/** Work runs outside BroadcastReceiver's time limit; uncertain adds keep their idempotency key. */
public final class WidgetJobService extends JobService {
    private final ExecutorService executor=Executors.newSingleThreadExecutor();
    private Future<?> task;
    @Override public boolean onStartJob(JobParameters params){
        task=executor.submit(()->{
            JobWorkItem item;
            while(!Thread.currentThread().isInterrupted()&&(item=params.dequeueWork())!=null){
                perform(item.getIntent().getStringExtra("scope"),item.getIntent().getBooleanExtra("add",false));
                if(Thread.currentThread().isInterrupted())return;
                params.completeWork(item);
            }
            // dequeueWork() completes the job when its queue is empty.
        });
        return true;
    }
    @Override public boolean onStopJob(JobParameters params){
        if(task!=null)task.cancel(true);
        CounterWidget.state(this).edit().putLong("busy_until",0).commit();CounterWidget.render(this);
        return true;
    }
    @Override public void onDestroy(){executor.shutdownNow();super.onDestroy();}
    private boolean current(String scope){return scope!=null&&!scope.isEmpty()&&scope.equals(CounterWidget.currentScope(this));}
    private void perform(String scope,boolean add){
        if(!current(scope))return;
        String server=CounterWidget.server(this),token=TokenStore.load(this),language=CounterWidget.language(this);
        SharedPreferences prefs=CounterWidget.state(this);boolean saved=false;
        try{
            PushSync.upload(this,server,token,language);
            String key=prefs.getString("pending_key","");
            if(add&&!key.isEmpty()){
                prefs.edit().putLong("busy_until",System.currentTimeMillis()+60000).commit();CounterWidget.render(this);
                JSONObject payload=new JSONObject().put("quantity",1).put("source","android").put("occurred_at",prefs.getString("pending_time",""));
                ApiClient.request(server,token,language,"/cigarettes","POST",payload,key);
                if(!current(scope))return;
                prefs.edit().remove("pending_key").remove("pending_time").commit();saved=true;
            }
            if(Thread.currentThread().isInterrupted()||!current(scope))return;
            JSONObject settings=(JSONObject)ApiClient.request(server,token,language,"/settings","GET",null,null);
            if(!current(scope))return;
            CounterWidget.preferences(this).edit().putString("language",settings.getString("language")).commit();
            JSONObject stats=(JSONObject)ApiClient.request(server,token,language,"/stats","GET",null,null);
            CounterWidget.acceptStats(this,server,token,stats);
        }catch(Exception error){
            if(!current(scope))return;
            if(error instanceof ApiClient.HttpError&&((ApiClient.HttpError)error).status==401){TokenStore.clear(this);}
            else {
                if(error instanceof ApiClient.HttpError){
                    int status=((ApiClient.HttpError)error).status;
                    if(status>=400&&status<500&&status!=429)prefs.edit().remove("pending_key").remove("pending_time").commit();
                }
                prefs.edit().putString("error",saved?"widget_saved":error instanceof ApiClient.HttpError?"widget_error":"widget_offline").commit();
            }
        }finally{
            if(current(scope))prefs.edit().putLong("busy_until",0).commit();
            CounterWidget.render(this);
        }
    }
}
