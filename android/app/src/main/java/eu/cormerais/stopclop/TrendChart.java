package eu.cormerais.stopclop;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.DashPathEffect;
import android.view.MotionEvent;
import android.view.View;
import java.text.NumberFormat;
import java.util.Locale;

/** Touch-selectable native chart. The screen also exposes every value as accessible text. */
final class TrendChart extends View {
    interface Selection {void select(int index);}
    private final double[] values;private final String[] labels;private final double average;private final boolean line;
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);private final NumberFormat format;
    private final Selection selection;private int selected=-1;private float left,right;
    TrendChart(Context c,double[] values,String[] labels,double average,boolean line,Locale locale,Selection selection){
        super(c);this.values=values;this.labels=labels;this.average=average;this.line=line;this.selection=selection;
        format=NumberFormat.getNumberInstance(locale);format.setMaximumFractionDigits(1);setFocusable(true);setClickable(true);
    }
    void step(int direction){select(selected+direction);}
    private float dp(float value){return Ui.dp(getContext(),value);}
    void select(int index){if(values.length==0)return;selected=Math.max(0,Math.min(index,values.length-1));selection.select(selected);invalidate();}
    @Override protected void onDraw(Canvas canvas){
        super.onDraw(canvas);if(values.length==0)return;
        left=dp(38);right=getWidth()-dp(8);float top=dp(20),bottom=getHeight()-dp(30),width=right-left;
        double largest=Math.max(1,average);for(double value:values)largest=Math.max(largest,value);
        double step=Math.pow(10,Math.floor(Math.log10(largest)));double max=Math.ceil(largest/step)*step;if(!line)max=Math.max(2,Math.ceil(max/2)*2);
        paint.setTypeface(android.graphics.Typeface.create("sans-serif",android.graphics.Typeface.NORMAL));paint.setTextSize(dp(10));paint.setStrokeWidth(dp(1));
        for(int i=0;i<=2;i++){
            float y=bottom-(bottom-top)*i/2;paint.setColor(Ui.BORDER);canvas.drawLine(left,y,right,y,paint);
            paint.setColor(Ui.MUTED);paint.setTextAlign(Paint.Align.RIGHT);canvas.drawText(format.format(max*i/2),left-dp(8),y+dp(3),paint);
        }
        float avgY=bottom-(float)(average/max)*(bottom-top);paint.setColor(Ui.MUTED);paint.setPathEffect(new DashPathEffect(new float[]{dp(4),dp(4)},0));canvas.drawLine(left,avgY,right,avgY,paint);paint.setPathEffect(null);
        float slot=width/values.length;Path path=new Path();
        for(int i=0;i<values.length;i++){
            float x=left+slot*(i+.5f),y=bottom-(float)(values[i]/max)*(bottom-top);
            if(line){if(i==0)path.moveTo(x,y);else path.lineTo(x,y);}
            else {paint.setColor(i==selected?Ui.ORANGE:Ui.GREEN);float bar=Math.max(dp(1),Math.min(dp(24),slot*.65f));canvas.drawRoundRect(x-bar/2,y,x+bar/2,bottom,dp(3),dp(3),paint);}
        }
        if(line){
            Path area=new Path(path);area.lineTo(right-slot/2,bottom);area.lineTo(left+slot/2,bottom);area.close();paint.setColor(0x22b75d39);canvas.drawPath(area,paint);
            paint.setColor(Ui.ORANGE);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(dp(2.5f));canvas.drawPath(path,paint);paint.setStyle(Paint.Style.FILL);
        }
        if(selected>=0){float x=left+slot*(selected+.5f),y=bottom-(float)(values[selected]/max)*(bottom-top);paint.setColor(Ui.ORANGE);canvas.drawCircle(x,y,dp(4),paint);}
        paint.setColor(Ui.MUTED);paint.setTextSize(dp(10));paint.setTextAlign(Paint.Align.LEFT);canvas.drawText(labels[0],left,getHeight()-dp(7),paint);
        paint.setTextAlign(Paint.Align.RIGHT);canvas.drawText(labels[labels.length-1],right,getHeight()-dp(7),paint);
    }
    @Override public boolean onTouchEvent(MotionEvent event){
        if(event.getAction()==MotionEvent.ACTION_UP){if(right>left)select((int)((event.getX()-left)/(right-left)*values.length));performClick();return true;}
        return event.getAction()==MotionEvent.ACTION_DOWN;
    }
    @Override public boolean performClick(){super.performClick();return true;}
}
