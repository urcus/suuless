package eu.cormerais.stopclop;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import org.json.JSONObject;
import org.unifiedpush.android.connector.UnifiedPush;

/** Push registrations are tied to the current account session, never shared between accounts. */
final class PushSync {
    static SharedPreferences state(Context context){return context.getSharedPreferences("push-sync",Context.MODE_PRIVATE);}
    static synchronized void reconcile(Context context){
        SharedPreferences prefs=state(context);String scope=CounterWidget.currentScope(context),old=prefs.getString("scope","");
        if(!scope.equals(old)){
            if(!old.isEmpty()&&prefs.getBoolean("enabled",false))UnifiedPush.unregister(context,old);
            prefs.edit().clear().putString("scope",scope).commit();
        }
    }
    static boolean current(Context context,String instance){return instance!=null&&!instance.isEmpty()&&instance.equals(CounterWidget.currentScope(context))&&state(context).getBoolean("enabled",false);}
    static boolean enabled(Context context){reconcile(context);return state(context).getBoolean("enabled",false);}
    static void enable(Activity activity){
        reconcile(activity);String scope=CounterWidget.currentScope(activity);
        if(scope.isEmpty())return;
        state(activity).edit().putBoolean("enabled",true).putString("status","push_registering").commit();
        UnifiedPush.tryUseCurrentOrDefaultDistributor(activity,success->{
            if(success&&current(activity,scope))UnifiedPush.register(activity,scope,"Stop Clop",null);
            else if(current(activity,scope))state(activity).edit().putString("status","push_registration_failed").commit();
            return kotlin.Unit.INSTANCE;
        });
    }
    static void disable(Context context){
        String scope=CounterWidget.currentScope(context);
        state(context).edit().putBoolean("enabled",false).remove("endpoint").remove("uploaded").putString("status","push_disabled").commit();
        if(!scope.isEmpty())UnifiedPush.unregister(context,scope);
    }
    static void renew(Context context){
        if(enabled(context)&&UnifiedPush.getSavedDistributor(context)!=null)
            UnifiedPush.register(context,CounterWidget.currentScope(context),"Stop Clop",null);
    }
    static void upload(Context context,String server,String token,String language) throws Exception {
        String scope=CounterWidget.scope(server,token);if(!current(context,scope))return;
        SharedPreferences prefs=state(context);String endpoint=prefs.getString("endpoint","");
        if(endpoint.isEmpty()||endpoint.equals(prefs.getString("uploaded","")))return;
        try{
            ApiClient.request(server,token,language,"/push","PUT",new JSONObject().put("endpoint",endpoint),null);
            if(current(context,scope))prefs.edit().putString("uploaded",endpoint).putString("status","push_active").commit();
        }catch(Exception error){
            if(current(context,scope))prefs.edit().putString("status","push_registration_failed").commit();
            if(error instanceof ApiClient.HttpError&&((ApiClient.HttpError)error).status==401)throw error;
        }
    }
}
