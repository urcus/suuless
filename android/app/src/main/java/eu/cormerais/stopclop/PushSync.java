package eu.cormerais.stopclop;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.PowerManager;
import android.provider.Settings;

/** Direct sync uses the existing encrypted session and server, without a distributor. */
final class PushSync {
    static SharedPreferences state(Context context){return context.getSharedPreferences("direct-sync",Context.MODE_PRIVATE);}
    static synchronized void reconcile(Context context){
        String scope=CounterWidget.currentScope(context);
        if(!scope.equals(state(context).getString("scope",""))){
            context.stopService(new Intent(context,DirectSyncService.class));
            state(context).edit().clear().putString("scope",scope).commit();
        }
    }
    static boolean current(Context context,String scope){return !scope.isEmpty()&&scope.equals(CounterWidget.currentScope(context))&&state(context).getBoolean("enabled",false);}
    static boolean enabled(Context context){reconcile(context);return state(context).getBoolean("enabled",false);}
    static boolean batteryAllowed(Context context){return context.getSystemService(PowerManager.class).isIgnoringBatteryOptimizations(context.getPackageName());}
    static void automatic(Activity activity){
        reconcile(activity);
        if(CounterWidget.currentScope(activity).isEmpty())return;
        if(!state(activity).contains("enabled"))state(activity).edit().putBoolean("enabled",true).commit();
        renew(activity);
        if(enabled(activity)&&!state(activity).getBoolean("asked",false)){
            state(activity).edit().putBoolean("asked",true).commit();
            permissions(activity);
        }
    }
    static void permissions(Activity activity){
        Translations t=new Translations(activity,CounterWidget.language(activity));
        new AlertDialog.Builder(activity).setTitle(t.text("push_enable")).setMessage(t.text("push_setup"))
            .setPositiveButton(t.text("sync_permissions"),(dialog,which)->{
                if(Build.VERSION.SDK_INT>=33&&activity.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)
                    activity.requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},7042);
                else requestBattery(activity);
            }).setNegativeButton(t.text("cancel"),null).show();
    }
    static void requestBattery(Activity activity){
        if(!batteryAllowed(activity)){
            Intent intent=new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,Uri.parse("package:"+activity.getPackageName()));
            try{activity.startActivity(intent);}catch(android.content.ActivityNotFoundException ignored){activity.startActivity(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));}
        }
        renew(activity);
    }
    static void enable(Activity activity){reconcile(activity);state(activity).edit().putBoolean("enabled",true).commit();renew(activity);permissions(activity);}
    static void disable(Context context){
        state(context).edit().putBoolean("enabled",false).putString("status","push_disabled").commit();
        context.stopService(new Intent(context,DirectSyncService.class));
    }
    static void renew(Context context){
        if(!enabled(context)||CounterWidget.currentScope(context).isEmpty())return;
        try{context.startForegroundService(new Intent(context,DirectSyncService.class));}
        catch(IllegalStateException|SecurityException error){state(context).edit().putString("status","sync_background_blocked").commit();}
    }
}
