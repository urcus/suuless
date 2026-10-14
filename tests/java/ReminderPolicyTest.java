package eu.cormerais.stopclop;
import java.time.ZonedDateTime;
public class ReminderPolicyTest {
    private static String slot(String instant,boolean enabled,int weekday,String time,String a,String b){return ReminderPolicy.slot(ZonedDateTime.parse(instant),enabled,time,weekday,a,b);}
    private static void same(String expected,String actual){if(!expected.equals(actual))throw new AssertionError(expected+" != "+actual);}
    public static void main(String[] args){
        same("",slot("2025-04-07T08:59:00+09:00",true,-1,"09:00","22:00","08:00"));
        same("2025-04-07",slot("2025-04-07T09:00:00+09:00",true,-1,"09:00","22:00","08:00"));
        same("",slot("2025-04-07T09:00:00+09:00",false,-1,"09:00","22:00","08:00"));
        same("2025-04-07",slot("2025-04-07T10:00:00+05:45",true,0,"10:00","22:00","08:00"));
        same("",slot("2025-04-08T10:00:00+05:45",true,0,"10:00","22:00","08:00"));
        same("",slot("2025-04-07T23:00:00Z",true,-1,"09:00","22:00","08:00"));
        same("",slot("2025-04-07T13:00:00Z",true,-1,"09:00","12:00","14:00"));
        same("2025-03-30",slot("2025-03-30T03:00:00+02:00[Europe/Paris]",true,-1,"02:30","00:00","00:00"));
        same("2025-10-26",slot("2025-10-26T02:45:00+02:00[Europe/Paris]",true,-1,"02:30","00:00","00:00"));
        same("2025-10-26",slot("2025-10-26T02:45:00+01:00[Europe/Paris]",true,-1,"02:30","00:00","00:00"));
        same("2026-01-01",slot("2026-01-01T00:10:00+12:45",true,-1,"00:01","00:00","00:00"));
        System.out.println("Reminder policy: 11 assertions passed (thresholds, weekday, quiet hours, fractional zones and DST).");
    }
}
