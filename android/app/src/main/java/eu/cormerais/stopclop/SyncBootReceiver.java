package eu.cormerais.stopclop;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Resume the user's choice after reboot/unlock or an in-place application update. */
public final class SyncBootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context,Intent intent){
        if(Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())||Intent.ACTION_MY_PACKAGE_REPLACED.equals(intent.getAction())){PushSync.renew(context);ReminderJobService.restore(context);}
    }
}
