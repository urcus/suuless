package eu.cormerais.stopclop;

import org.unifiedpush.android.connector.PushService;
import org.unifiedpush.android.connector.FailedReason;
import org.unifiedpush.android.connector.data.PushEndpoint;
import org.unifiedpush.android.connector.data.PushMessage;
import java.nio.charset.StandardCharsets;

/** The connector verifies distributor IPC; the payload is only an invalidation hint. */
public final class WidgetPushService extends PushService {
    @Override public void onNewEndpoint(PushEndpoint endpoint,String instance){
        if(!PushSync.current(this,instance))return;
        PushSync.state(this).edit().putString("endpoint",endpoint.getUrl()).putString("status",endpoint.getUrl().equals(PushSync.state(this).getString("uploaded",""))?"push_active":"push_registering").commit();
        CounterWidget.enqueue(this,false);
    }
    @Override public void onMessage(PushMessage message,String instance){
        if(PushSync.current(this,instance)&&"refresh".equals(new String(message.getContent(),StandardCharsets.UTF_8)))
            CounterWidget.enqueue(this,false);
    }
    @Override public void onRegistrationFailed(FailedReason reason,String instance){
        if(PushSync.current(this,instance))PushSync.state(this).edit().putString("status","push_registration_failed").commit();
    }
    @Override public void onUnregistered(String instance){
        if(PushSync.current(this,instance))PushSync.state(this).edit().remove("uploaded").remove("endpoint").putString("status","push_registration_failed").commit();
    }
}
