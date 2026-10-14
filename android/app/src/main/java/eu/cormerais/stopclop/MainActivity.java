package eu.cormerais.stopclop;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.widget.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.net.URI;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.ArrayList;
import java.text.NumberFormat;
import java.time.format.FormatStyle;
import android.text.TextWatcher;
import android.text.Editable;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Native Android client. The server is the single source of truth. */
public final class MainActivity extends Activity {
    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private LinearLayout content;
    private TextView status;
    private String server = "", token = "", zone = "Europe/Paris", page = "dashboard";
    private boolean trendSmoothed = false;
    private int historyDays = 0;
    private int days = 30, historyOffset = 0;
    private boolean busy = false;
    private String pendingKey = null, pendingPayload = null;
    private String rangeStart, rangeEnd, localNow;
    private String pendingExport;
    private String language = "en";
    private Translations translations;
    private JSONObject catalog, snapshot;
    private boolean chartCost=false;
    private String chartCurrency="";
    private String t(String key, Object... args) { return translations.text(key, args); }
    private Locale locale() { return Locale.forLanguageTag(language); }
    private String number(double value) { return NumberFormat.getNumberInstance(locale()).format(value); }
    private void setLanguage(String code) {
        language = code; translations = new Translations(this, code);
        getPreferences(MODE_PRIVATE).edit().putString("language", code).apply();
    }
    interface Work { Object run() throws Exception; }
    interface Done { void accept(Object value) throws Exception; }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        if(android.os.Build.VERSION.SDK_INT>=27)getWindow().getDecorView().setSystemUiVisibility(getWindow().getDecorView().getSystemUiVisibility()|View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        setLanguage(getPreferences(MODE_PRIVATE).getString("language", "en"));
        server = getPreferences(MODE_PRIVATE).getString("server", ""); token = TokenStore.load(this);
        if (state != null) { pendingExport = state.getString("pendingExport"); pendingKey = state.getString("pendingKey"); pendingPayload = state.getString("pendingPayload"); }
        if (token.isEmpty()) login(); else { dashboard(); }
    }
    @Override public void onRequestPermissionsResult(int requestCode,String[] permissions,int[] results){
        super.onRequestPermissionsResult(requestCode,permissions,results);
        if(requestCode==7042)PushSync.requestBattery(this);
    }
    @Override protected void onResume(){super.onResume();PushSync.renew(this);}
    @Override protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out); out.putString("pendingExport",pendingExport); out.putString("pendingKey", pendingKey); out.putString("pendingPayload", pendingPayload);
    }
    @Override protected void onRestart() {
        super.onRestart();
        // Returning from the launcher must include additions made through the widget.
        if (!busy && page.equals("dashboard")) {
            token = TokenStore.load(this);
            if (token.isEmpty()) login(); else dashboard();
        }
    }
    @Override protected void onDestroy() { network.shutdownNow(); super.onDestroy(); }
    private int dp(int n) { return (int) (n * getResources().getDisplayMetrics().density); }
    private void screen(String title) {
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setBackgroundColor(Ui.PAPER);
        root.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());return insets;});
        LinearLayout header=new LinearLayout(this);header.setGravity(android.view.Gravity.CENTER_VERTICAL);header.setPadding(dp(24),dp(14),dp(24),dp(6));
        ImageView logo=new ImageView(this);logo.setImageResource(R.drawable.ic_brand);logo.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        LinearLayout.LayoutParams logoSize=new LinearLayout.LayoutParams(dp(36),dp(36));logoSize.setMarginEnd(dp(10));header.addView(logo,logoSize);
        TextView brand=Ui.label(this,t("app_name"),20,Ui.INK,true);header.addView(brand,new LinearLayout.LayoutParams(0,-2,1));
        if(!page.equals("login")&&!page.equals("entry")){
            Button refresh=Ui.button(this,"↻",false,()->{if(!busy)reload();});refresh.setContentDescription(t("refresh"));header.addView(refresh,new LinearLayout.LayoutParams(dp(48),dp(48)));
        }
        root.addView(header);
        status=Ui.label(this,"",13,Ui.ORANGE,false);status.setPadding(dp(24),dp(8),dp(24),dp(8));status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);status.setVisibility(View.GONE);root.addView(status);
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setClipToPadding(false);
        content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);content.setPadding(dp(24),dp(8),dp(24),dp(20));scroll.addView(content);
        root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        if(!page.equals("login")){
            LinearLayout nav=new LinearLayout(this);nav.setPadding(dp(12),dp(6),dp(12),dp(8));nav.setBackgroundColor(Ui.WHITE);
            String[] pages={"dashboard","analysis","history","settings"},keys={"nav_today","nav_analysis","history","settings"};
            for(int i=0;i<4;i++){
                final String target=pages[i];boolean active=page.equals(target)||(page.equals("entry")&&i==2);
                LinearLayout item=new LinearLayout(this);item.setOrientation(LinearLayout.VERTICAL);item.setGravity(android.view.Gravity.CENTER);item.setPadding(dp(3),dp(8),dp(3),dp(8));
                item.setBackground(Ui.shape(this,active?Ui.MINT:Ui.WHITE,18));item.addView(new Ui.Icon(this,i,active?Ui.GREEN:Ui.MUTED),new LinearLayout.LayoutParams(dp(24),dp(24)));
                TextView label=Ui.label(this,t(keys[i]),11,active?Ui.GREEN:Ui.MUTED,active);label.setGravity(android.view.Gravity.CENTER);item.addView(label);
                item.setContentDescription(t(keys[i]));item.setFocusable(true);item.setClickable(true);item.setSelected(active);item.setOnClickListener(v->{if(!busy&&!page.equals(target))navigate(target);});
                nav.addView(item,new LinearLayout.LayoutParams(0,-2,1));
            }
            root.addView(nav);
        }
        setContentView(root);root.requestApplyInsets();text(title,29);
    }
    private void setStatus(String value){status.setText(value);status.setVisibility(value==null||value.isEmpty()?View.GONE:View.VISIBLE);}
    private void navigate(String target){if(target.equals("analysis"))analytics();else if(target.equals("history"))history();else if(target.equals("settings"))settings();else dashboard();}
    private void reload(){navigate(page);}
    @Override public void onBackPressed(){if(!page.equals("dashboard")&&!page.equals("login")&&!busy)dashboard();else super.onBackPressed();}
    private TextView text(String value,int size){TextView v=Ui.label(this,value,size,size>=20?Ui.INK:Ui.MUTED,size>=20);v.setPadding(0,dp(6),0,dp(8));content.addView(v);return v;}
    private TextView cardText(LinearLayout card,String value,int size,int color,boolean bold){TextView v=Ui.label(this,value,size,color,bold);v.setPadding(0,dp(3),0,dp(4));card.addView(v);return v;}
    private LinearLayout card(int color){LinearLayout c=Ui.card(this,color);content.addView(c);return c;}
    private EditText input(String label,String value,int type){
        TextView caption=text(label,13);EditText field=new EditText(this);field.setId(View.generateViewId());caption.setLabelFor(field.getId());field.setSingleLine(true);field.setInputType(type);field.setText(value);field.setTextSize(16);field.setTextColor(Ui.INK);
        field.setPadding(dp(14),dp(14),dp(14),dp(14));field.setBackground(Ui.shape(this,Ui.WHITE,12));LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);params.setMargins(0,0,0,dp(12));content.addView(field,params);return field;
    }
    private Button button(String label,Runnable action){Button b=Ui.button(this,label,label.equals(t("save"))||label.equals(t("login"))||label.equals(t("plus_one")),()->{if(!busy)action.run();});content.addView(b);return b;}
    private void perform(Work work, Done done) {
        if (busy) return; busy = true; setStatus(t("connecting"));
        network.execute(() -> {
            try {
                Object value = work.run();
                runOnUiThread(() -> { if (isDestroyed()) return; busy = false; setStatus("");
                    try { done.accept(value); } catch (Exception e) { setStatus(e.getMessage()); }
                });
            } catch (Exception error) {
                runOnUiThread(() -> { if (isDestroyed()) return; busy = false;
                    if (error instanceof ExpiredSession) { token = ""; TokenStore.clear(this); login(); }
                    setStatus(error instanceof java.io.IOException ? t("network_error") : error.getMessage());
                });
            }
        });
    }
    private static class ExpiredSession extends Exception { ExpiredSession(String message) { super(message); } }
    private Object api(String path, String method, JSONObject data, String key) throws Exception {
        try { return ApiClient.request(server, token, language, path, method, data, key); }
        catch (ApiClient.HttpError error) {
            if(error.status>=400&&error.status<500&&path.equals("/cigarettes")){pendingKey=null;pendingPayload=null;}
            if(error.status==401&&!path.startsWith("/auth/"))throw new ExpiredSession(error.getMessage());
            throw error;
        }
    }
    private JSONObject get(String path) throws Exception { return (JSONObject) api(path, "GET", null, null); }
    private String money(double value, String code) throws Exception {
        int digits = 2;
        if (catalog != null) {
            JSONArray currencies = catalog.getJSONArray("currencies");
            for (int i = 0; i < currencies.length(); i++) {
                JSONObject currency = currencies.getJSONObject(i);
                if (currency.getString("code").equals(code)) { digits = currency.getInt("digits"); break; }
            }
        }
        NumberFormat format = NumberFormat.getNumberInstance(locale());
        format.setMinimumFractionDigits(digits); format.setMaximumFractionDigits(digits);
        return code + " " + format.format(value);
    }
    private String costs(JSONObject data) throws Exception {
        JSONObject amounts = data.getJSONObject("costs"); ArrayList<String> values = new ArrayList<>();
        ArrayList<String> codes = new ArrayList<>(); amounts.keys().forEachRemaining(codes::add); java.util.Collections.sort(codes);
        for (String code : codes) values.add(money(amounts.getDouble(code), code));
        return String.join(" · ", values);
    }
    private String dateLabel(String iso) {
        return LocalDate.parse(iso).format(DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT).withLocale(locale()));
    }
    private void login() {
        page = "login"; PushSync.reconcile(this); CounterWidget.render(this); screen(t("personal_space"));
        EditText address = input(t("server_address"), server.isEmpty() ? "https://" : server, InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        EditText username = input(t("username"), "", InputType.TYPE_CLASS_TEXT);
        EditText password = input(t("password"), "", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        EditText email = input(t("registration_email"), "", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);
        text(t("password_help"), 13);
        for (boolean register : new boolean[]{false, true}) {
            button(register ? t("register") : t("login"), () -> {
                try {
                    String base = address.getText().toString().trim().replaceAll("/+$", ""); URI uri = new URI(base);
                    if (uri.getHost() == null || !("https".equals(uri.getScheme()) || "http".equals(uri.getScheme())) ||
                        uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null || !uri.getPath().isEmpty())
                        throw new Exception(t("server_address_error"));
                    server = base;
                    JSONObject payload = new JSONObject().put("username", username.getText().toString()).put("password", password.getText().toString()).put("language", language).put("client", "android");
                    perform(() -> {
                        if (register) {
                            payload.put("email", email.getText().toString().trim());
                            JSONObject choices = get("/config");
                            String detected = java.util.TimeZone.getDefault().getID();
                            detected = choices.getJSONObject("timezone_aliases").optString(detected, detected);
                            JSONArray ids = choices.getJSONArray("timezones"); boolean supported = false;
                            for (int i = 0; i < ids.length(); i++) if (ids.getString(i).equals(detected)) supported = true;
                            payload.put("timezone", supported ? detected : "UTC");
                        }
                        return api(register ? "/auth/register" : "/auth/login", "POST", payload, null);
                    }, value -> {
                        if (((JSONObject)value).optBoolean("activation_required")) { password.setText(""); setStatus(t("email_requested")); return; }
                        token = ((JSONObject)value).getString("token"); TokenStore.save(this, token);
                        getPreferences(MODE_PRIVATE).edit().putString("server", server).apply(); password.setText(""); dashboard();
                    });
                } catch (Exception e) { setStatus(e.getMessage()); }
            });
        }
        button(t("forgot_password"), () -> {
            try {
                URI url=new URI(address.getText().toString().trim().replaceAll("/+$", ""));
                if(url.getHost()==null || !("https".equals(url.getScheme())||"http".equals(url.getScheme())) || url.getUserInfo()!=null || url.getQuery()!=null || url.getFragment()!=null || !url.getPath().isEmpty())throw new Exception(t("server_address_error"));
                startActivity(new android.content.Intent(android.content.Intent.ACTION_VIEW,android.net.Uri.parse(url.toString()+"/account?mode=forgot")));
            }catch(Exception e){setStatus(e.getMessage());}
        });
        button(t("language") + " · " + language, () -> new AlertDialog.Builder(this).setTitle(t("language"))
            .setItems(new String[]{"English", "Français", "日本語"}, (dialog, index) -> {
                server = address.getText().toString(); setLanguage(new String[]{"en","fr","ja"}[index]); login();
            }).show());

    }
    private void openCoaching(boolean craving){startActivity(new android.content.Intent(this,CoachingActivity.class).putExtra("craving",craving));}
    @Override protected void onNewIntent(android.content.Intent intent){super.onNewIntent(intent);setIntent(intent);if(!busy&&!token.isEmpty()&&intent.getBooleanExtra("open_coaching_craving",false)){intent.removeExtra("open_coaching_craving");openCoaching(true);}}
    private String range() { return "?start=" + rangeStart + "&end=" + rangeEnd; }
    private void dashboard(){loadSnapshot("dashboard");}
    private void analytics(){loadSnapshot("analysis");}
    private void loadSnapshot(String target){
        page=target;screen(t(target.equals("dashboard")?"nav_today":"nav_analysis"));
        perform(()->{
            JSONObject me=get("/me");
            if("admin".equals(me.optString("role")))return new JSONObject().put("admin",true);
            JSONObject prefs=get("/settings");zone=prefs.getString("timezone");
            LocalDate end=LocalDate.parse(prefs.getString("local_today"));localNow=prefs.getString("local_datetime");rangeEnd=end.toString();rangeStart=end.minusDays(days-1).toString();
            catalog=get("/config");JSONObject push;
            try{push=get("/sync/config");push.put("enabled",true);}catch(ApiClient.HttpError error){if(error.status!=404)throw error;push=new JSONObject().put("enabled",false);}
            JSONObject stats=get("/stats"+range());historyDays=stats.optInt("history_days",0);
            if(days>7&&historyDays<days){days=7;rangeStart=end.minusDays(6).toString();stats=get("/stats"+range());}
            return new JSONObject().put("push",push).put("settings",prefs).put("stats",stats);
        },value->{
            if(((JSONObject)value).optBoolean("admin")){
                page="login";screen(t("admin_title"));text(t("admin_browser"),16);
                button(t("admin_title"),()->startActivity(new android.content.Intent(android.content.Intent.ACTION_VIEW,android.net.Uri.parse(server+"/admin"))));
                button(t("logout"),()->perform(()->api("/auth/logout","POST",null,null),unused->{token="";TokenStore.clear(this);login();}));return;
            }
            snapshot=(JSONObject)value;setLanguage(snapshot.getJSONObject("settings").getString("language"));ReminderJobService.configure(this,snapshot.getJSONObject("settings"));CounterWidget.acceptStats(this,server,token,snapshot.getJSONObject("stats"));
            if(target.equals("analysis"))renderAnalysis();else renderToday();
            if(getIntent().getBooleanExtra("open_coaching_craving",false)){getIntent().removeExtra("open_coaching_craving");openCoaching(true);}
            else if(snapshot.getJSONObject("push").optBoolean("enabled"))PushSync.automatic(this);
        });
    }
    private void renderToday() throws Exception {
        screen(t("nav_today"));JSONObject stats=snapshot.getJSONObject("stats"),today=stats.getJSONObject("today"),prefs=snapshot.getJSONObject("settings"),analysis=stats.getJSONObject("analysis");
        text(LocalDate.parse(rangeEnd).format(DateTimeFormatter.ofPattern("EEEE d MMMM",locale()))+" · "+zone,13);
        LinearLayout hero=card(Ui.GREEN);cardText(hero,t("daily_consumption"),14,Ui.MINT,false);
        cardText(hero,number(today.getInt("quantity")),64,Ui.WHITE,true);cardText(hero,t("cigarettes"),16,Ui.MINT,false);
        Button add=Ui.button(this,t("plus_one"),false,()->{if(!busy)addOne();});hero.addView(add);
        hero.addView(Ui.button(this,t("craving_button"),false,()->{if(!busy)openCoaching(true);}));
        button(t("journey_title"),()->openCoaching(false));
        boolean chosen=prefs.has("coaching_goal")&&!prefs.isNull("coaching_goal");int target=chosen?prefs.getInt("coaching_goal"):prefs.getInt("daily_target");
        if(target>0){ProgressBar progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);progress.setMax(target);progress.setProgress(Math.min(today.getInt("quantity"),target));progress.setProgressTintList(android.content.res.ColorStateList.valueOf(Ui.MINT));progress.setProgressBackgroundTintList(android.content.res.ColorStateList.valueOf(0xff426858));progress.setContentDescription(t("target_label",number(target)));hero.addView(progress,new LinearLayout.LayoutParams(-1,dp(8)));}
        cardText(hero,chosen?t("goal_today",number(target),number(today.getInt("quantity"))):t("target_label",number(target)),12,Ui.MINT,false);
        if(pendingPayload!=null)button(t("retry_entry"),()->{try{submit(new JSONObject(pendingPayload));}catch(Exception e){setStatus(e.getMessage());}});
        LinearLayout cost=card(Ui.WHITE);cardText(cost,t("spent_today"),13,Ui.MUTED,false);cardText(cost,costs(today),28,Ui.INK,true);
        cardText(cost,t("average",number(analysis.getDouble("average_quantity_per_day")),number(days)),13,Ui.MUTED,false);
        LinearLayout trend=card(Ui.WHITE);cardText(trend,t("week_at_glance"),20,Ui.INK,true);
        JSONArray daily=stats.getJSONArray("daily"),week=new JSONArray();for(int i=Math.max(0,daily.length()-7);i<daily.length();i++)week.put(daily.getJSONObject(i));
        double average=0;for(int i=0;i<week.length();i++)average+=week.getJSONObject(i).getDouble("quantity");average/=Math.max(1,week.length());
        chart(trend,week,false,"",average,false);
        trend.addView(Ui.button(this,t("explore_analysis"),false,()->{if(!busy)analytics();}));
        button(t("past_entry"),this::entryForm);
    }
    private void periodChips(){
        LinearLayout row=new LinearLayout(this);content.addView(row);
        for(int count:new int[]{7,30,90}){Button b=Ui.button(this,t("short_days",number(count)),days==count,()->{if(!busy){days=count;navigate(page);}});LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,-2,1);p.setMargins(dp(3),dp(6),dp(3),dp(8));row.addView(b,p);b.setSelected(days==count);if(count>7&&historyDays<count){b.setEnabled(false);b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(Ui.BORDER));b.setTextColor(Ui.MUTED);b.setContentDescription(t("short_days",number(count))+" · "+t("waiting_data"));}}
        if(historyDays<90)text(t("waiting_data")+" · "+t("history_wait",number(historyDays)),12);
    }
    private String signed(double value){return (value>0?"+":"")+number(value);}
    private void renderAnalysis() throws Exception {
        screen(t("nav_analysis"));periodChips();button(t("export_share"),this::exportConsumption);JSONObject stats=snapshot.getJSONObject("stats"),analysis=stats.getJSONObject("analysis"),comparison=analysis.getJSONObject("comparison"),period=stats.getJSONObject("period");
        text(dateLabel(rangeStart)+" — "+dateLabel(rangeEnd),13);
        LinearLayout summary=card(Ui.GREEN);cardText(summary,t("average_daily_quantity"),13,Ui.MINT,false);cardText(summary,number(analysis.getDouble("average_quantity_per_day")),38,Ui.WHITE,true);
        String percent=comparison.isNull("quantity_percent")?t("percent_unavailable"):signed(comparison.getDouble("quantity_percent"))+" %";
        cardText(summary,percent+" · "+t("previous_comparison"),13,Ui.MINT,false);
        LinearLayout chartCard=card(Ui.WHITE);cardText(chartCard,t("evolution"),20,Ui.INK,true);
        LinearLayout measures=new LinearLayout(this);chartCard.addView(measures);
        for(boolean cost:new boolean[]{false,true}){Button b=Ui.button(this,t(cost?"cost":"quantity"),chartCost==cost,()->{chartCost=cost;try{renderAnalysis();}catch(Exception e){setStatus(e.getMessage());}});LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(0,-2,1);params.setMargins(dp(3),dp(6),dp(3),dp(6));measures.addView(b,params);b.setSelected(chartCost==cost);}
        ArrayList<String> codes=new ArrayList<>();analysis.getJSONObject("average_cost_per_day").keys().forEachRemaining(codes::add);java.util.Collections.sort(codes);
        if(!codes.contains(chartCurrency))chartCurrency=codes.contains(snapshot.getJSONObject("settings").getString("currency"))?snapshot.getJSONObject("settings").getString("currency"):codes.get(0);
        if(chartCost){
            LinearLayout old=content;content=chartCard;Spinner picker=select("chart_currency",codes,codes.indexOf(chartCurrency));content=old;
            picker.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onNothingSelected(AdapterView<?> p){}public void onItemSelected(AdapterView<?> p,View v,int position,long id){String selected=codes.get(position);if(!selected.equals(chartCurrency)){chartCurrency=selected;try{renderAnalysis();}catch(Exception e){setStatus(e.getMessage());}}}});
        }
        if(analysis.has("trend")){Switch smooth=new Switch(this);smooth.setText(t("trend_smooth"));smooth.setChecked(trendSmoothed);chartCard.addView(smooth);smooth.setOnCheckedChangeListener((button,checked)->{trendSmoothed=checked;try{renderAnalysis();}catch(Exception e){setStatus(e.getMessage());}});if(trendSmoothed)cardText(chartCard,t("trend_note"),12,Ui.MUTED,false);}
        chart(chartCard,analysis.getJSONArray(trendSmoothed&&analysis.has("trend")?"trend":"daily"),chartCost,chartCurrency,chartCost?analysis.getJSONObject("average_cost_per_day").getDouble(chartCurrency):analysis.getDouble("average_quantity_per_day"),true);
        cardText(chartCard,t("average_legend"),12,Ui.MUTED,false);
        chartCard.addView(Ui.button(this,t("daily_figures"),false,()->dailyFigures(analysis)));
        LinearLayout spending=card(Ui.PEACH);cardText(spending,t("average_daily_cost"),13,Ui.ORANGE,false);
        for(String code:codes){cardText(spending,money(analysis.getJSONObject("average_cost_per_day").getDouble(code),code),27,Ui.INK,true);
            JSONObject percentages=comparison.getJSONObject("cost_percent");String delta=percentages.isNull(code)?t("percent_unavailable"):signed(percentages.getDouble(code))+" %";
            cardText(spending,delta+" · "+t("previous_comparison"),12,Ui.MUTED,false);}
        renderHabits(analysis);
        LinearLayout totals=card(Ui.WHITE);cardText(totals,t("period_total"),12,Ui.MUTED,false);cardText(totals,t("quantity_count",number(period.getInt("quantity")))+" · "+costs(period),21,Ui.INK,true);
        cardText(totals,t("all_time"),12,Ui.MUTED,false);cardText(totals,t("quantity_count",number(stats.getJSONObject("total").getInt("quantity")))+" · "+costs(stats.getJSONObject("total")),19,Ui.INK,true);
        JSONObject previous=analysis.getJSONObject("previous_period");
        text(t("previous_dates",dateLabel(previous.getString("start")),dateLabel(previous.getString("end"))),12);
        text(t("analysis_range",number(analysis.getInt("minimum_quantity")),number(analysis.getInt("maximum_quantity")),number(analysis.getInt("days_with_entries"))),12);
        text(t("analysis_basis"),12);if(analysis.optBoolean("includes_today"))text(t("day_in_progress"),12);text(t("empty_day_note"),12);
    }
    private void renderHabits(JSONObject analysis) throws Exception {
        // Older servers can still serve the existing dashboard during a rolling upgrade.
        if(!analysis.has("hourly"))return;
        LinearLayout habits=card(Ui.WHITE);cardText(habits,t("habits_title"),20,Ui.INK,true);
        cardText(habits,t("habits_note",zone),12,Ui.MUTED,false);
        cardText(habits,t("hourly_title"),17,Ui.INK,true);
        JSONArray hours=analysis.getJSONArray("hourly");double[] values=new double[24];String[] labels=new String[24];StringBuilder figures=new StringBuilder();
        int peak=0;for(int i=0;i<24;i++){JSONObject hour=hours.getJSONObject(i);values[i]=hour.getDouble("quantity");labels[i]=String.format(Locale.ROOT,"%02d",i)+":00";if(values[i]>values[peak])peak=i;
            figures.append(t("hourly_value",String.format(Locale.ROOT,"%02d",i),number(values[i]),number(hour.getDouble("share_percent")))).append("\n\n");}
        if(values[peak]==0)cardText(habits,t("habits_empty"),13,Ui.MUTED,false);
        TextView selected=Ui.label(this,"",14,Ui.INK,true);selected.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        TrendChart hourly=new TrendChart(this,values,labels,0,false,locale(),index->{try{selected.setText(t("hourly_value",String.format(Locale.ROOT,"%02d",index),number(values[index]),number(hours.getJSONObject(index).getDouble("share_percent"))));}catch(Exception e){setStatus(e.getMessage());}});
        hourly.setContentDescription(t("hourly_title")+". "+t("hourly_figures"));habits.addView(hourly,new LinearLayout.LayoutParams(-1,dp(180)));habits.addView(selected);hourly.select(peak);
        habits.addView(Ui.button(this,t("hourly_figures"),false,()->new AlertDialog.Builder(this).setTitle(t("hourly_title")).setMessage(figures.toString()).setPositiveButton(t("back"),null).show()));
        cardText(habits,t("weekday_title"),17,Ui.INK,true);cardText(habits,t("weekday_note"),12,Ui.MUTED,false);
        JSONArray weekdays=analysis.getJSONArray("weekdays");double max=1;for(int i=0;i<weekdays.length();i++)max=Math.max(max,weekdays.getJSONObject(i).optDouble("average",0));
        for(int i=0;i<weekdays.length();i++){JSONObject day=weekdays.getJSONObject(i);String name=DayOfWeek.of(day.getInt("weekday")+1).getDisplayName(java.time.format.TextStyle.FULL,locale());
            String label=day.isNull("average")?name+" · "+t("no_sample"):t("weekday_value",name,number(day.getDouble("average")),number(day.getInt("days")));
            cardText(habits,label,13,Ui.INK,false);ProgressBar bar=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);bar.setMax(1000);bar.setProgress((int)(day.optDouble("average",0)/max*1000));bar.setProgressTintList(android.content.res.ColorStateList.valueOf(Ui.GREEN));bar.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);habits.addView(bar,new LinearLayout.LayoutParams(-1,dp(8)));}
        JSONObject projection=analysis.getJSONObject("projection");LinearLayout estimate=card(Ui.PEACH);cardText(estimate,t("projection_title"),19,Ui.INK,true);
        if(projection.isNull("quantity")){cardText(estimate,t("projection_empty"),13,Ui.MUTED,false);return;}
        cardText(estimate,t("quantity_count",number(projection.getDouble("quantity"))),27,Ui.INK,true);cardText(estimate,costs(projection),22,Ui.ORANGE,true);
        cardText(estimate,t("projection_note",number(projection.getInt("sample_days"))),12,Ui.MUTED,false);
    }
    private void chart(LinearLayout parent,JSONArray daily,boolean cost,String currency,double average,boolean details) throws Exception {
        double[] values=new double[daily.length()];String[] labels=new String[daily.length()];
        for(int i=0;i<daily.length();i++){JSONObject day=daily.getJSONObject(i);values[i]=cost?day.getJSONObject("costs").optDouble(currency,0):day.getDouble("quantity");labels[i]=LocalDate.parse(day.getString("date")).format(DateTimeFormatter.ofPattern("d MMM",locale()));}
        TextView selected=Ui.label(this,"",14,Ui.INK,true);selected.setPadding(0,dp(8),0,dp(4));selected.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        TrendChart chart=new TrendChart(this,values,labels,average,cost,locale(),index->{
            try{JSONObject day=daily.getJSONObject(index);String label=dateLabel(day.getString("date"))+" · "+(cost?money(values[index],currency):t("quantity_count",number(values[index])));
                if(details){double delta=cost?day.getJSONObject("cost_deltas").optDouble(currency,0):day.getDouble("quantity_delta");label+="\n"+signed(delta)+(cost?" "+currency:"")+" · "+t(cost?"cost_difference":"quantity_difference");}
                selected.setText(label);
            }catch(Exception e){setStatus(e.getMessage());}
        });
        chart.setContentDescription(t("chart_accessibility"));parent.addView(chart,new LinearLayout.LayoutParams(-1,dp(details?220:150)));parent.addView(selected);chart.select(Math.max(0,daily.length()-1));
        if(details){LinearLayout controls=new LinearLayout(this);for(int direction:new int[]{-1,1}){Button b=Ui.button(this,t(direction<0?"previous_day":"next_day"),false,()->{chart.step(direction);});LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(0,-2,1);params.setMargins(dp(3),0,dp(3),0);controls.addView(b,params);}parent.addView(controls);}
    }
    private void dailyFigures(JSONObject analysis){
        try{JSONArray days=analysis.getJSONArray("daily");StringBuilder data=new StringBuilder();for(int i=days.length()-1;i>=0;i--){JSONObject day=days.getJSONObject(i);data.append(dateLabel(day.getString("date"))).append(" · ").append(t("quantity_count",number(day.getInt("quantity")))).append("\n").append(costs(day)).append("\n\n");}
            new AlertDialog.Builder(this).setTitle(t("daily_figures")).setMessage(data.toString()).setPositiveButton(t("back"),null).show();
        }catch(Exception e){setStatus(e.getMessage());}
    }
    private void addOne() {
        try { submit(new JSONObject().put("source", "android")); } catch (Exception e) { setStatus(e.getMessage()); }
    }
    private void submit(JSONObject payload) throws Exception {
        String serialized = payload.toString();
        if (pendingKey != null && !serialized.equals(pendingPayload)) {
            setStatus(t("pending_entry")); return;
        }
        if (pendingKey == null) { pendingKey = UUID.randomUUID().toString(); pendingPayload = serialized; }
        perform(() -> api("/cigarettes", "POST", payload, pendingKey), value -> {
            pendingKey = null; pendingPayload = null; Toast.makeText(this, t("entry_saved"), Toast.LENGTH_SHORT).show(); dashboard();
        });
    }
    private void entryForm() {
        page = "entry"; screen(t("complete_history"));
        EditText quantity = input(t("quantity"), "1", InputType.TYPE_CLASS_NUMBER);
        EditText date = input(t("local_datetime"), OffsetDateTime.parse(localNow).toLocalDateTime().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")), InputType.TYPE_CLASS_TEXT);
        button(t("choose_datetime"),()->{
            LocalDateTime initial;try{initial=LocalDateTime.parse(date.getText().toString(),DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm"));}catch(Exception e){initial=OffsetDateTime.parse(localNow).toLocalDateTime();}
            final LocalDateTime selected=initial;
            new android.app.DatePickerDialog(this,(picker,y,m,d)->new android.app.TimePickerDialog(this,(clock,h,min)->date.setText(LocalDateTime.of(y,m+1,d,h,min).format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm"))),selected.getHour(),selected.getMinute(),true).show(),initial.getYear(),initial.getMonthValue()-1,initial.getDayOfMonth()).show();
        });
        text(t("entry_zone_note", zone), 14);
        String[] triggerCodes={"","coffee","stress","meal","social","boredom","other"};ArrayList<String> triggerLabels=new ArrayList<>();for(String code:triggerCodes){String key=code.isEmpty()?"trigger_none":"trigger_"+code;triggerLabels.add(t(key));}Spinner trigger=select("craving_trigger",triggerLabels,0);
        button(t("save"), () -> {
            try {
                LocalDateTime local = LocalDateTime.parse(date.getText().toString(), DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm").withResolverStyle(java.time.format.ResolverStyle.STRICT));
                submit(new JSONObject().put("quantity", Integer.parseInt(quantity.getText().toString())).put("source", "android").put("occurred_at_local", local.toString()).put("trigger",triggerCodes[trigger.getSelectedItemPosition()]));
            } catch (Exception e) { setStatus(t("invalid_input")); }
        });
        button(t("back"), this::dashboard);
    }
    private void history(){
        if(rangeEnd==null){dashboard();return;}
        page="history";historyOffset=0;if(rangeEnd!=null)rangeStart=LocalDate.parse(rangeEnd).minusDays(days-1).toString();screen(t("history"));periodChips();text(dateLabel(rangeStart)+" — "+dateLabel(rangeEnd),13);button(t("past_entry"),this::entryForm);button(t("export_share"),this::exportConsumption);loadEntries();
    }
    private void exportConsumption(){
        new AlertDialog.Builder(this).setTitle(t("export_choose_period"))
            .setItems(new String[]{t("last_7"),t("last_30"),t("last_90")},(dialog,index)->exportConsumptionFormat(new int[]{7,30,90}[index]))
            .setNegativeButton(t("close_export"),null).show();
    }
    private void exportConsumptionFormat(int exportDays){
        new AlertDialog.Builder(this).setTitle(t("export_share")+" · "+t("short_days",number(exportDays))).setItems(new String[]{t("download_csv"),t("consumption_report")},(dialog,choice)->{
            final String extension=choice==0?"csv":"html",mime=choice==0?"text/csv":"text/html";
            perform(()->{
                LocalDate end=LocalDate.parse(get("/settings").getString("local_today"));
                String selectedRange="?start="+end.minusDays(exportDays-1)+"&end="+end;
                String body=(String)api((choice==0?"/export.csv":"/report.html")+selectedRange,"GET",null,null);
                java.io.File file=ExportProvider.file(this,"suuless-"+UUID.randomUUID()+"."+extension);
                java.io.File dir=file.getParentFile();if(!dir.isDirectory()&&!dir.mkdirs())throw new java.io.IOException();
                java.io.File[] old=dir.listFiles();if(old!=null)for(java.io.File f:old)if(f.lastModified()<System.currentTimeMillis()-86400000L)f.delete();
                try(java.io.FileOutputStream out=new java.io.FileOutputStream(file)){out.write(body.getBytes(java.nio.charset.StandardCharsets.UTF_8));}
                return file;
            },value->{
                java.io.File file=(java.io.File)value;
                new AlertDialog.Builder(this).setTitle(t("export_share")).setMessage(t("export_note")+(choice==1?"\n\n"+t("report_print_help"):""))
                    .setPositiveButton(t("save_file"),(d,w)->{
                        pendingExport=file.getName();
                        startActivityForResult(new android.content.Intent(android.content.Intent.ACTION_CREATE_DOCUMENT).addCategory(android.content.Intent.CATEGORY_OPENABLE).setType(mime).putExtra(android.content.Intent.EXTRA_TITLE,"suuless-"+(choice==0?"consumption":"report")+"-"+exportDays+"d."+extension),87);
                    })
                    .setNeutralButton(t(choice==0?"share_csv":"share_report"),(d,w)->{
                        android.net.Uri uri=new android.net.Uri.Builder().scheme("content").authority(getPackageName()+".exports").appendPath(file.getName()).build();
                        android.content.Intent intent=new android.content.Intent(android.content.Intent.ACTION_SEND).setType(mime).putExtra(android.content.Intent.EXTRA_STREAM,uri).addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION);
                        intent.setClipData(android.content.ClipData.newRawUri("SuuLess",uri));
                        startActivity(android.content.Intent.createChooser(intent,t("export_share")));
                    }).setNegativeButton(t("close_export"),null).show();
            });
        }).show();
    }
    @Override protected void onActivityResult(int requestCode,int resultCode,android.content.Intent result){
        super.onActivityResult(requestCode,resultCode,result);
        if(requestCode!=87)return;
        final String name=pendingExport;pendingExport=null;
        if(resultCode!=RESULT_OK||result==null||result.getData()==null||name==null)return;
        final android.net.Uri destination=result.getData();
        perform(()->{
            try(java.io.InputStream in=new java.io.FileInputStream(ExportProvider.file(this,name));java.io.OutputStream out=getContentResolver().openOutputStream(destination,"wt")){
                if(out==null)throw new java.io.IOException();byte[] buffer=new byte[8192];int n;while((n=in.read(buffer))!=-1)out.write(buffer,0,n);
            }return null;
        },value->Toast.makeText(this,t("export_saved"),Toast.LENGTH_SHORT).show());
    }
    private void loadEntries(){
        perform(()->get("/cigarettes"+range()+"&limit=30&offset="+historyOffset),value->{
            JSONObject result=(JSONObject)value;JSONArray items=result.getJSONArray("items");
            if(items.length()==0)text(t("no_entries"),16);
            for(int i=0;i<items.length();i++){
                JSONObject row=items.getJSONObject(i);int id=row.getInt("id");LinearLayout item=card(Ui.WHITE);
                OffsetDateTime date=OffsetDateTime.parse(row.getString("local_datetime"));
                cardText(item,date.format(DateTimeFormatter.ofPattern("EEE d MMM · HH:mm",locale())),13,Ui.MUTED,false);
                cardText(item,t("quantity_count",number(row.getInt("quantity"))),23,Ui.INK,true);
                cardText(item,money(row.getDouble("cost"),row.getString("currency"))+" · "+row.getString("source"),14,Ui.MUTED,false);
                Button remove=Ui.button(this,t("delete"),false,()->{if(!busy)new AlertDialog.Builder(this).setMessage(t("delete_confirm")).setNegativeButton(t("cancel"),null).setPositiveButton(t("delete"),(d,w)->perform(()->api("/cigarettes/"+id,"DELETE",null,null),unused->history())).show();});item.addView(remove);
            }
            historyOffset+=items.length();
            if(historyOffset<result.getInt("total")){Button more=button(t("more"),()->{});more.setOnClickListener(v->{if(!busy){content.removeView(more);loadEntries();}});}
        });
    }
    private Spinner select(String key, ArrayList<String> labels, int selected) {
        TextView caption = text(t(key), 14); Spinner spinner = new Spinner(this);
        spinner.setId(View.generateViewId()); caption.setLabelFor(spinner.getId());
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, labels);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spinner.setAdapter(adapter); spinner.setSelection(Math.max(0, selected)); spinner.setBackground(Ui.dropdown(this)); spinner.setPadding(dp(12),dp(8),dp(38),dp(8)); content.addView(spinner,new LinearLayout.LayoutParams(-1,dp(56))); return spinner;
    }
    private String searchKey(String value) {
        return java.text.Normalizer.normalize(value, java.text.Normalizer.Form.NFKD)
            .replaceAll("\\p{M}", "").toLowerCase(Locale.ROOT);
    }
    private void timezonePicker(Button target) {
        try {
            ArrayList<JSONObject> zones = new ArrayList<>(); JSONArray data = catalog.getJSONArray("timezone_options");
            String selected = (String)target.getTag(); boolean found = false;
            for (int i = 0; i < data.length(); i++) {
                JSONObject option = data.getJSONObject(i); zones.add(option);
                if (option.getString("id").equals(selected)) found = true;
            }
            if (!found) zones.add(new JSONObject().put("id", selected).put("label", target.getText()).put("search", selected));
            ArrayList<JSONObject> visible = new ArrayList<>(zones);
            ArrayList<String> labels = new ArrayList<>(); for (JSONObject option : zones) labels.add(option.getString("label"));
            LinearLayout layout = new LinearLayout(this); layout.setOrientation(LinearLayout.VERTICAL); layout.setPadding(dp(16),0,dp(16),0);
            EditText search = new EditText(this); search.setHint(t("search_timezone")); search.setSingleLine(true); layout.addView(search);
            ListView list = new ListView(this); ArrayAdapter<String> adapter = new ArrayAdapter<>(this, android.R.layout.simple_list_item_1, labels);
            list.setAdapter(adapter); layout.addView(list, new LinearLayout.LayoutParams(-1,dp(360)));
            AlertDialog dialog = new AlertDialog.Builder(this).setTitle(t("timezone")).setView(layout).setNegativeButton(t("cancel"), null).create();
            search.addTextChangedListener(new TextWatcher() {
                public void beforeTextChanged(CharSequence s,int start,int count,int after) {}
                public void onTextChanged(CharSequence s,int start,int before,int count) {
                    String query = searchKey(s.toString().trim()); visible.clear(); adapter.clear();
                    for (JSONObject option : zones) {
                        if (searchKey(option.optString("search") + " " + option.optString("label")).contains(query)) {
                            visible.add(option); adapter.add(option.optString("label"));
                        }
                    }
                    adapter.notifyDataSetChanged();
                }
                public void afterTextChanged(Editable e) {}
            });
            list.setOnItemClickListener((parent, view, position, id) -> {
                JSONObject option = visible.get(position); target.setText(option.optString("label")); target.setTag(option.optString("id")); dialog.dismiss();
            });
            dialog.show();
        } catch (Exception error) { setStatus(t("invalid_input")); }
    }
    private void confirmAccountDeletion() {
        LinearLayout fields=new LinearLayout(this);fields.setOrientation(LinearLayout.VERTICAL);fields.setPadding(dp(24),dp(12),dp(24),0);
        fields.addView(Ui.label(this,t("account_delete_note"),14,Ui.MUTED,false));
        EditText password=new EditText(this);password.setHint(t("password"));password.setContentDescription(t("password"));
        password.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        password.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(256)});fields.addView(password);
        CheckBox confirm=new CheckBox(this);confirm.setText(t("account_delete_confirm"));fields.addView(confirm);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle(t("delete_account")).setView(fields)
            .setNegativeButton(t("back"),null).setPositiveButton(t("delete_account_permanently"),null).create();
        dialog.setOnShowListener(ignored->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{
            if(password.getText().length()==0||!confirm.isChecked()){password.setError(t("account_delete_invalid"));return;}
            final String secret=password.getText().toString();password.setText("");dialog.dismiss();
            perform(()->api("/me","DELETE",new JSONObject().put("password",secret).put("confirm",true),null),unused->{
                token="";pendingKey=null;pendingPayload=null;snapshot=null;
                TokenStore.clear(this);PushSync.disable(this);
                for(String name:new String[]{"coaching-pending","coaching-reminders","counter-widget"})getSharedPreferences(name,MODE_PRIVATE).edit().clear().apply();
                CounterWidget.enqueue(this,false);login();Toast.makeText(this,t("account_deleted"),Toast.LENGTH_LONG).show();
            });
        }));dialog.show();
    }

    private void settings() {
        page = "settings"; screen(t("my_preferences"));
        perform(() -> new JSONObject().put("prefs", get("/settings")).put("catalog", get("/config")), value -> {
            JSONObject result = (JSONObject)value, prefs = result.getJSONObject("prefs"); catalog = result.getJSONObject("catalog");
            setLanguage(prefs.getString("language"));
            screen(t("my_preferences")); text(t("preferences_intro"),14); text(t("regional_preferences"),20);
            ArrayList<String> languageCodes = new ArrayList<>(), languageLabels = new ArrayList<>();
            JSONArray languages = catalog.getJSONArray("languages");
            for (int i = 0; i < languages.length(); i++) { JSONObject item = languages.getJSONObject(i); languageCodes.add(item.getString("code")); languageLabels.add(item.getString("name")); }
            Spinner languageInput = select("language", languageLabels, languageCodes.indexOf(prefs.getString("language")));
            ArrayList<String> codes = new ArrayList<>(), labels = new ArrayList<>(); JSONArray currencies = catalog.getJSONArray("currencies");
            for (int i = 0; i < currencies.length(); i++) { JSONObject item = currencies.getJSONObject(i); codes.add(item.getString("code")); labels.add(item.getString("code") + " — " + item.getString("name")); }
            Spinner currency = select("currency", labels, codes.indexOf(prefs.getString("currency")));
            text(t("price_preferences"),20);
            EditText price = input(t("pack_price"), prefs.getString("pack_price"), InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
            TextView hint = text(t("currency_price_hint", prefs.getString("currency")), 13);
            final String[] previousCurrency = {prefs.getString("currency")};
            currency.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
                public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                    String selected = codes.get(position);
                    if (!selected.equals(previousCurrency[0])) { price.setText(""); previousCurrency[0] = selected; }
                    hint.setText(t("currency_price_hint", selected));
                }
                public void onNothingSelected(AdapterView<?> parent) {}
            });
            EditText size = input(t("pack_size"), prefs.getString("pack_size"), InputType.TYPE_CLASS_NUMBER);
            EditText target = input(t("daily_target"), prefs.getString("daily_target"), InputType.TYPE_CLASS_NUMBER);
            text(t("time_preferences"),20);
            TextView zoneLabel = text(t("timezone"), 14);
            Button timezone = button(prefs.getJSONObject("timezone_info").getString("label"), () -> {}); timezone.setTag(prefs.getString("timezone")); timezone.setId(View.generateViewId()); zoneLabel.setLabelFor(timezone.getId());
            timezone.setOnClickListener(v -> { if (!busy) timezonePicker(timezone); });
            text(t("price_note"), 14); text(t("web_integrations"), 14);
            button(t("save"), () -> {
                try {
                    String amount = new java.math.BigDecimal(price.getText().toString().replace(',', '.')).toPlainString();
                    JSONObject payload = new JSONObject().put("pack_price", amount).put("currency", codes.get(currency.getSelectedItemPosition()))
                        .put("language", languageCodes.get(languageInput.getSelectedItemPosition())).put("pack_size", Integer.parseInt(size.getText().toString()))
                        .put("daily_target", Integer.parseInt(target.getText().toString())).put("timezone", (String)timezone.getTag());
                    // Only save edits from this form; another device may have changed other preferences.
                    JSONObject changes = new JSONObject();
                    for (String key : new String[]{"language", "pack_size", "daily_target", "timezone"}) {
                        if (!payload.getString(key).equals(prefs.getString(key))) changes.put(key, payload.get(key));
                    }
                    if (!payload.getString("currency").equals(prefs.getString("currency")) ||
                        new java.math.BigDecimal(amount).compareTo(new java.math.BigDecimal(prefs.getString("pack_price"))) != 0) {
                        changes.put("currency", payload.getString("currency")).put("pack_price", amount);
                    }
                    perform(() -> api("/settings", "PUT", changes, null), saved -> {
                        setLanguage(((JSONObject)saved).getString("language")); Toast.makeText(this, t("settings_saved"), Toast.LENGTH_SHORT).show(); dashboard();
                    });
                } catch (Exception e) { setStatus(t("invalid_input")); }
            });
            text(t("sync_preferences"),20);
            text(t(PushSync.state(this).getString("status","push_disabled")),14);
            button(t("sync_permissions"),()->PushSync.permissions(this));
            if(PushSync.enabled(this))button(t("push_disable"),()->{PushSync.disable(this);settings();});
            else button(t("push_enable"),()->{PushSync.enable(this);settings();});
            button(t("widget_add_home"),()->{android.appwidget.AppWidgetManager manager=android.appwidget.AppWidgetManager.getInstance(this);if(manager.isRequestPinAppWidgetSupported())manager.requestPinAppWidget(new android.content.ComponentName(this,CounterWidget.class),null,null);else Toast.makeText(this,t("widget_pin_help"),Toast.LENGTH_LONG).show();});
            text(t("account_preferences"),20);text(server,13);
            button(t("delete_account"),()->{if(!busy)confirmAccountDeletion();});
            button(t("logout"),()->perform(()->api("/auth/logout","POST",null,null),unused->{token="";pendingKey=null;pendingPayload=null;snapshot=null;TokenStore.clear(this);login();}));
        });
    }
}
