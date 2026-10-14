package eu.cormerais.stopclop;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.IBinder;
import android.os.PowerManager;
import org.json.JSONObject;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** User-visible live widget synchronization, independent of JobScheduler during Doze. */
public final class DirectSyncService extends Service {
    private static final String CHANNEL="widget-sync",STOP="stop-sync";
    private volatile boolean stopped;
    private volatile HttpURLConnection connection;
    private Thread worker;
    @Override public IBinder onBind(Intent intent){return null;}
    private void notification(){
        Translations t=new Translations(this,CounterWidget.language(this));
        getSystemService(NotificationManager.class).createNotificationChannel(new NotificationChannel(CHANNEL,t.text("sync_notification_title"),NotificationManager.IMPORTANCE_LOW));
        PendingIntent open=PendingIntent.getActivity(this,7042,new Intent(this,MainActivity.class),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        PendingIntent stop=PendingIntent.getService(this,7043,new Intent(this,DirectSyncService.class).setAction(STOP),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        startForeground(7042,new Notification.Builder(this,CHANNEL).setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(t.text("sync_notification_title")).setContentText(t.text("sync_notification_body"))
            .setContentIntent(open).setOngoing(true).setOnlyAlertOnce(true)
            .addAction(new Notification.Action.Builder(null,t.text("push_disable"),stop).build()).build());
    }
    @Override public int onStartCommand(Intent intent,int flags,int startId){
        if(intent!=null&&STOP.equals(intent.getAction())){PushSync.disable(this);stopSelf();return START_NOT_STICKY;}
        if(!PushSync.enabled(this)){stopSelf();return START_NOT_STICKY;}
        notification();
        if(worker==null){worker=new Thread(this::listen,"widget-direct-sync");worker.start();}
        return START_STICKY;
    }
    private void status(String scope,String value){if(PushSync.current(this,scope))PushSync.state(this).edit().putString("status",value).apply();}
    private void refresh(String scope,String server,String token) throws Exception {
        if(!PushSync.current(this,scope))return;
        PowerManager.WakeLock lock=getSystemService(PowerManager.class).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"SuuLess:refresh");
        lock.acquire(30000);
        try{
        String language=CounterWidget.language(this);
        JSONObject settings=(JSONObject)ApiClient.request(server,token,language,"/settings","GET",null,null);
        if(!PushSync.current(this,scope))return;
        CounterWidget.preferences(this).edit().putString("language",settings.getString("language")).commit();
        ReminderJobService.configure(this,settings);
        JSONObject stats=(JSONObject)ApiClient.request(server,token,language,"/stats","GET",null,null);
        CounterWidget.acceptStats(this,server,token,stats);
        }finally{if(lock.isHeld())lock.release();}
    }
    private boolean dayChanged(){
        try{return !java.time.LocalDate.now(java.time.ZoneId.of(CounterWidget.state(this).getString("zone","UTC"))).toString().equals(CounterWidget.state(this).getString("day",""));}
        catch(Exception ignored){return false;}
    }
    private void listen(){
        String server=CounterWidget.server(this),token=TokenStore.load(this),scope=CounterWidget.scope(server,token);
        String cursor="";int failures=0;long lastRefresh=0;
        while(!stopped&&PushSync.current(this,scope)){
            try{
                status(scope,"push_registering");
                HttpURLConnection stream=(HttpURLConnection)new URL(server+"/api/sync/events").openConnection();connection=stream;
                stream.setConnectTimeout(5000);stream.setReadTimeout(25000);stream.setInstanceFollowRedirects(false);stream.setUseCaches(false);
                stream.setRequestProperty("Authorization","Bearer "+token);stream.setRequestProperty("Accept","text/event-stream");
                if(!cursor.isEmpty())stream.setRequestProperty("Last-Event-ID",cursor);
                int code=stream.getResponseCode();
                if(code==503)failures=Math.max(failures,4); // Honor the server's 30-second capacity backoff.
                if(code==401)throw new ApiClient.HttpError(401,"Session expired");
                if(code!=200||!String.valueOf(stream.getContentType()).startsWith("text/event-stream"))throw new java.io.IOException("Sync unavailable");
                status(scope,"push_active");
                try(BufferedReader reader=new BufferedReader(new InputStreamReader(stream.getInputStream(),StandardCharsets.UTF_8))){
                    String line,event="",id="";
                    while(!stopped&&PushSync.current(this,scope)&&(line=reader.readLine())!=null){
                        if(line.length()>1024)throw new java.io.IOException("Invalid event");
                        if(line.startsWith("id: "))id=line.substring(4);
                        else if(line.startsWith("event: "))event=line.substring(7);
                        else if(line.isEmpty()){
                            if("revoked".equals(event))throw new ApiClient.HttpError(401,"Session expired");
                            if("refresh".equals(event)||System.currentTimeMillis()-lastRefresh>900000||dayChanged()){
                                refresh(scope,server,token);lastRefresh=System.currentTimeMillis();
                                if(id.matches("[0-9a-f]{32}"))cursor=id;
                            }
                            failures=0;event="";id="";
                        }
                    }
                }
            }catch(Exception error){
                if(error instanceof ApiClient.HttpError&&((ApiClient.HttpError)error).status==401){
                    if(PushSync.current(this,scope)){TokenStore.clear(this);CounterWidget.render(this);}break;
                }
                status(scope,"sync_reconnecting");failures=Math.min(failures+1,6);
            }finally{HttpURLConnection stream=connection;connection=null;if(stream!=null)stream.disconnect();}
            try{Thread.sleep(Math.min(60000,1000L<<failures));}catch(InterruptedException interrupted){break;}
        }
        stopSelf();
    }
    @Override public void onDestroy(){
        stopped=true;if(worker!=null)worker.interrupt();
        HttpURLConnection stream=connection;if(stream!=null)stream.disconnect();
        super.onDestroy();
    }
}
