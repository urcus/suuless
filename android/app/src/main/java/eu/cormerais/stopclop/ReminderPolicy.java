package eu.cormerais.stopclop;

import java.time.LocalTime;
import java.time.ZonedDateTime;

/** Calendar slots, not elapsed 24-hour intervals. One slot survives a repeated DST hour. */
final class ReminderPolicy {
    static String slot(ZonedDateTime now,boolean enabled,String scheduled,int weekday,String quietStart,String quietEnd){
        if(!enabled||(weekday>=0&&now.getDayOfWeek().getValue()-1!=weekday))return "";
        LocalTime at=now.toLocalTime(),start=LocalTime.parse(quietStart),end=LocalTime.parse(quietEnd);
        boolean quiet=start.isBefore(end)?!at.isBefore(start)&&at.isBefore(end):start.isAfter(end)&&(!at.isBefore(start)||at.isBefore(end));
        if(quiet||at.isBefore(LocalTime.parse(scheduled)))return "";
        return now.toLocalDate().toString();
    }
}
