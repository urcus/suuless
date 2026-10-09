package eu.cormerais.stopclop;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Small native design system shared by the screens and charts. */
final class Ui {
    static final int PAPER=0xfff4f5f0,INK=0xff193d33,MUTED=0xff607267,GREEN=0xff204e40,MINT=0xffdcebdc,
        BORDER=0xffe3e8df,WHITE=0xffffffff,ORANGE=0xff9b4b2d,PEACH=0xfff7e6da;
    static int dp(Context c,float value){return Math.round(value*c.getResources().getDisplayMetrics().density);}
    static GradientDrawable shape(Context c,int color,int radius){GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(c,radius));return d;}
    static TextView label(Context c,String text,int size,int color,boolean bold){
        TextView v=new TextView(c);v.setText(text);v.setTextSize(size);v.setTextColor(color);
        v.setTypeface(Typeface.create(bold?"sans-serif-medium":"sans-serif",Typeface.NORMAL));v.setLineSpacing(dp(c,2),1);return v;
    }
    static LinearLayout card(Context c,int color){
        LinearLayout v=new LinearLayout(c);v.setOrientation(LinearLayout.VERTICAL);v.setPadding(dp(c,20),dp(c,20),dp(c,20),dp(c,20));v.setBackground(shape(c,color,24));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.setMargins(0,dp(c,8),0,dp(c,8));v.setLayoutParams(p);return v;
    }
    static Button button(Context c,String text,boolean primary,Runnable action){
        Button b=new Button(c);b.setText(text);b.setAllCaps(false);b.setTextSize(15);b.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));
        b.setTextColor(primary?WHITE:INK);b.setMinHeight(dp(c,50));b.setMinimumHeight(dp(c,50));b.setPadding(dp(c,16),dp(c,10),dp(c,16),dp(c,10));
        b.setBackground(new RippleDrawable(ColorStateList.valueOf(0x22204e40),shape(c,primary?GREEN:MINT,15),null));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.setMargins(0,dp(c,6),0,dp(c,6));b.setLayoutParams(p);b.setOnClickListener(v->action.run());return b;
    }
    static android.graphics.drawable.Drawable dropdown(Context context){
        android.graphics.drawable.Drawable arrow=new android.graphics.drawable.Drawable(){
            final Paint p=new Paint(Paint.ANTI_ALIAS_FLAG);
            @Override public void draw(Canvas c){p.setColor(MUTED);p.setStrokeWidth(dp(context,2));p.setStyle(Paint.Style.STROKE);float x=getBounds().right-dp(context,24),y=getBounds().exactCenterY();Path path=new Path();path.moveTo(x-dp(context,4),y-dp(context,2));path.lineTo(x,y+dp(context,2));path.lineTo(x+dp(context,4),y-dp(context,2));c.drawPath(path,p);}
            @Override public void setAlpha(int alpha){p.setAlpha(alpha);}
            @Override public void setColorFilter(android.graphics.ColorFilter filter){p.setColorFilter(filter);}
            @Override public int getOpacity(){return android.graphics.PixelFormat.TRANSLUCENT;}
        };
        return new android.graphics.drawable.LayerDrawable(new android.graphics.drawable.Drawable[]{shape(context,WHITE,12),arrow});
    }
    static class Icon extends View {
        final int kind,color; final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        Icon(Context c,int kind,int color){super(c);this.kind=kind;this.color=color;setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);}
        @Override protected void onDraw(Canvas c){
            super.onDraw(c);c.save();c.translate((getWidth()-dp(getContext(),24))/2f,(getHeight()-dp(getContext(),24))/2f);c.scale(dp(getContext(),24)/24f,dp(getContext(),24)/24f);
            paint.setColor(color);paint.setStrokeWidth(1.8f);paint.setStyle(Paint.Style.STROKE);paint.setStrokeCap(Paint.Cap.ROUND);paint.setStrokeJoin(Paint.Join.ROUND);Path p=new Path();
            if(kind==0){p.moveTo(3,10);p.lineTo(12,3);p.lineTo(21,10);p.moveTo(5,9);p.lineTo(5,21);p.lineTo(10,21);p.lineTo(10,14);p.lineTo(14,14);p.lineTo(14,21);p.lineTo(19,21);p.lineTo(19,9);c.drawPath(p,paint);}
            else if(kind==1){c.drawLine(4,20,4,13,paint);c.drawLine(10,20,10,7,paint);c.drawLine(16,20,16,11,paint);c.drawLine(22,20,22,3,paint);}
            else if(kind==2){c.drawCircle(12,12,9,paint);p.moveTo(12,6);p.lineTo(12,12);p.lineTo(16,14);c.drawPath(p,paint);}
            else {for(int y=6;y<=18;y+=6){c.drawLine(3,y,21,y,paint);paint.setStyle(Paint.Style.FILL);c.drawCircle(y==12?15:8,y,3,paint);paint.setStyle(Paint.Style.STROKE);}}
            c.restore();
        }
    }
}
