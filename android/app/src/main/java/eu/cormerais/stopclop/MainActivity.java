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
    private int days = 30, historyOffset = 0;
    private boolean busy = false;
    private String pendingKey = null, pendingPayload = null;
    private String rangeStart, rangeEnd, localNow;
    private String language = "en";
    private Translations translations;
    private JSONObject catalog;
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
        setLanguage(getPreferences(MODE_PRIVATE).getString("language", "en"));
        server = getPreferences(MODE_PRIVATE).getString("server", ""); token = TokenStore.load(this);
        if (state != null) { pendingKey = state.getString("pendingKey"); pendingPayload = state.getString("pendingPayload"); }
        if (token.isEmpty()) login(); else { dashboard(); }
    }
    @Override public void onRequestPermissionsResult(int requestCode,String[] permissions,int[] results){
        super.onRequestPermissionsResult(requestCode,permissions,results);
        if(requestCode==7042)PushSync.requestBattery(this);
    }
    @Override protected void onResume(){super.onResume();PushSync.renew(this);}
    @Override protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out); out.putString("pendingKey", pendingKey); out.putString("pendingPayload", pendingPayload);
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
        LinearLayout root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setBackgroundColor(0xfff5f5ef);
        root.setPadding(dp(20), dp(16), dp(20), dp(12));
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            v.setPadding(dp(20) + insets.getSystemWindowInsetLeft(), dp(16) + insets.getSystemWindowInsetTop(),
                dp(20) + insets.getSystemWindowInsetRight(), dp(12) + insets.getSystemWindowInsetBottom()); return insets;
        });
        TextView brand = new TextView(this); brand.setText("◉ stop clop"); brand.setTextSize(27); brand.setTextColor(0xff163d32); root.addView(brand);
        status = new TextView(this); status.setTextSize(14); status.setPadding(0, dp(10), 0, dp(10)); status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE); root.addView(status);
        ScrollView scroll = new ScrollView(this); content = new LinearLayout(this); content.setOrientation(LinearLayout.VERTICAL); scroll.addView(content);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1)); setContentView(root); root.requestApplyInsets();
        text(title, 26);
    }
    private TextView text(String value, int size) {
        TextView v = new TextView(this); v.setText(value); v.setTextSize(size); v.setTextColor(0xff213d35); v.setPadding(0, dp(10), 0, dp(10)); content.addView(v); return v;
    }
    private EditText input(String label, String value, int type) {
        TextView caption = text(label, 14);
        EditText field = new EditText(this); field.setId(View.generateViewId()); caption.setLabelFor(field.getId());
        field.setSingleLine(true); field.setInputType(type); field.setText(value); content.addView(field); return field;
    }
    private Button button(String label, Runnable action) {
        Button b = new Button(this); b.setText(label); b.setAllCaps(false); b.setOnClickListener(v -> { if (!busy) action.run(); }); content.addView(b); return b;
    }
    private void perform(Work work, Done done) {
        if (busy) return; busy = true; status.setText(t("connecting"));
        network.execute(() -> {
            try {
                Object value = work.run();
                runOnUiThread(() -> { if (isDestroyed()) return; busy = false; status.setText("");
                    try { done.accept(value); } catch (Exception e) { status.setText(e.getMessage()); }
                });
            } catch (Exception error) {
                runOnUiThread(() -> { if (isDestroyed()) return; busy = false;
                    if (error instanceof ExpiredSession) { token = ""; TokenStore.clear(this); login(); }
                    status.setText(error instanceof java.io.IOException ? t("network_error") : error.getMessage());
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
        return String.join(" + ", values);
    }
    private String dateLabel(String iso) {
        return LocalDate.parse(iso).format(DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT).withLocale(locale()));
    }
    private void login() {
        page = "login"; PushSync.reconcile(this); CounterWidget.render(this); screen(t("personal_space"));
        EditText address = input(t("server_address"), server.isEmpty() ? "https://" : server, InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        EditText username = input(t("username"), "", InputType.TYPE_CLASS_TEXT);
        EditText password = input(t("password"), "", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        text(t("password_help"), 13);
        for (boolean register : new boolean[]{false, true}) {
            button(register ? t("register") : t("login"), () -> {
                try {
                    String base = address.getText().toString().trim().replaceAll("/+$", ""); URI uri = new URI(base);
                    if (uri.getHost() == null || !("https".equals(uri.getScheme()) || "http".equals(uri.getScheme())) ||
                        uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null || !uri.getPath().isEmpty())
                        throw new Exception(t("server_address_error"));
                    server = base;
                    JSONObject payload = new JSONObject().put("username", username.getText().toString()).put("password", password.getText().toString()).put("language", language);
                    perform(() -> {
                        if (register) {
                            JSONObject choices = get("/config");
                            String detected = java.util.TimeZone.getDefault().getID();
                            detected = choices.getJSONObject("timezone_aliases").optString(detected, detected);
                            JSONArray ids = choices.getJSONArray("timezones"); boolean supported = false;
                            for (int i = 0; i < ids.length(); i++) if (ids.getString(i).equals(detected)) supported = true;
                            payload.put("timezone", supported ? detected : "UTC");
                        }
                        return api(register ? "/auth/register" : "/auth/login", "POST", payload, null);
                    }, value -> {
                        token = ((JSONObject)value).getString("token"); TokenStore.save(this, token);
                        getPreferences(MODE_PRIVATE).edit().putString("server", server).apply(); password.setText(""); dashboard();
                    });
                } catch (Exception e) { status.setText(e.getMessage()); }
            });
        }
        button(t("language") + " · " + language, () -> new AlertDialog.Builder(this).setTitle(t("language"))
            .setItems(new String[]{"English", "Français", "日本語"}, (dialog, index) -> {
                server = address.getText().toString(); setLanguage(new String[]{"en","fr","ja"}[index]); login();
            }).show());
        text(t("android_https"), 13);
    }
    private String range() { return "?start=" + rangeStart + "&end=" + rangeEnd; }
    private void dashboard() {
        page = "dashboard"; screen(t("tagline"));
        button(t("refresh"), this::dashboard);
        perform(() -> {
            JSONObject prefs = get("/settings"); zone = prefs.getString("timezone");
            LocalDate end = LocalDate.parse(prefs.getString("local_today")); localNow = prefs.getString("local_datetime"); rangeEnd = end.toString(); rangeStart = end.minusDays(days - 1).toString();
            catalog = get("/config");
            JSONObject push;
            try { push=get("/sync/config"); push.put("enabled",true); } catch(ApiClient.HttpError error) { if(error.status!=404)throw error; push=new JSONObject().put("enabled",false); }
            return new JSONObject().put("push",push).put("settings", prefs).put("stats", get("/stats" + range()));
        }, value -> {
            JSONObject bundle = (JSONObject)value, stats = bundle.getJSONObject("stats"), today = stats.getJSONObject("today"), period = stats.getJSONObject("period"), total = stats.getJSONObject("total");
            setLanguage(bundle.getJSONObject("settings").getString("language"));
            CounterWidget.acceptStats(this, server, token, stats);
            screen(t("tagline")); button(t("refresh"), this::dashboard);
            // Currency names and precision come from the same catalog as the web app.
            if (catalog == null) { catalog = new JSONObject(); catalog.put("currencies", new JSONArray()); }
            text(t("today") + " · " + zone, 15); text(t("quantity_count", number(today.getInt("quantity"))), 38); text(costs(today), 25);
            button(t("plus_one"), () -> addOne());
            if (pendingPayload != null) button(t("retry_entry"), () -> { try { submit(new JSONObject(pendingPayload)); } catch (Exception e) { status.setText(e.getMessage()); } });
            text(t("target_label", number(bundle.getJSONObject("settings").getInt("daily_target"))), 14);
            text(t("last_days", number(days)), 23);
            text(t("quantity_count", number(period.getInt("quantity"))) + " · " + costs(period) + "\n" + t("average", number(period.getDouble("average_per_day")), number(days)), 19);
            text(t("all_time") + " : " + t("quantity_count", number(total.getInt("quantity"))) + " · " + costs(total), 18);
            button(t("change_period"), () -> new AlertDialog.Builder(this).setTitle(t("period")).setItems(new String[]{t("last_7"), t("last_30"), t("last_90")}, (d, index) -> { days = new int[]{7,30,90}[index]; dashboard(); }).show());
            button(t("past_entry"), this::entryForm);
            button(t("history_daily"), this::history);
            button(t("settings"), this::settings);
            if(bundle.getJSONObject("push").optBoolean("enabled")) {
                PushSync.automatic(this);
                text(t(PushSync.state(this).getString("status","push_disabled")),14);
                if(PushSync.enabled(this)){
                    button(t("sync_permissions"),()->PushSync.permissions(this));
                    button(t("push_disable"),()->{PushSync.disable(this);dashboard();});
                }else button(t("push_enable"),()->{PushSync.enable(this);dashboard();});
            }
            button(t("widget_add_home"), () -> {
                android.appwidget.AppWidgetManager manager=android.appwidget.AppWidgetManager.getInstance(this);
                if(manager.isRequestPinAppWidgetSupported())manager.requestPinAppWidget(new android.content.ComponentName(this,CounterWidget.class),null,null);
                else Toast.makeText(this,t("widget_pin_help"),Toast.LENGTH_LONG).show();
            });

            button(t("logout"), () -> perform(() -> api("/auth/logout", "POST", null, null), unused -> { token = ""; pendingKey = null; pendingPayload = null; TokenStore.clear(this); login(); }));
        });
    }
    private void addOne() {
        try { submit(new JSONObject().put("source", "android")); } catch (Exception e) { status.setText(e.getMessage()); }
    }
    private void submit(JSONObject payload) throws Exception {
        String serialized = payload.toString();
        if (pendingKey != null && !serialized.equals(pendingPayload)) {
            status.setText(t("pending_entry")); return;
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
        text(t("entry_zone_note", zone), 14);
        button(t("save"), () -> {
            try {
                LocalDateTime local = LocalDateTime.parse(date.getText().toString(), DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm").withResolverStyle(java.time.format.ResolverStyle.STRICT));
                submit(new JSONObject().put("quantity", Integer.parseInt(quantity.getText().toString())).put("source", "android").put("occurred_at_local", local.toString()));
            } catch (Exception e) { status.setText(t("invalid_input")); }
        });
        button(t("back"), this::dashboard);
    }
    private void history() {
        page = "history"; historyOffset = 0; screen(t("last_days", number(days)));
        button(t("back_dashboard"), this::dashboard);
        perform(() -> get("/stats" + range()), value -> {
            JSONArray daily = ((JSONObject)value).getJSONArray("daily");
            for (int i = daily.length() - 1; i >= 0; i--) { JSONObject day = daily.getJSONObject(i); text(dateLabel(day.getString("date")) + " · " + t("quantity_count", number(day.getInt("quantity"))) + " · " + costs(day), 15); }
            text(t("empty_day_note"), 13);
            text(t("history"), 23); loadEntries();
        });
    }
    private void loadEntries() {
        perform(() -> get("/cigarettes" + range() + "&limit=30&offset=" + historyOffset), value -> {
            JSONObject result = (JSONObject)value; JSONArray items = result.getJSONArray("items");
            if (items.length() == 0) text(t("no_entries"), 16);
            for (int i = 0; i < items.length(); i++) {
                JSONObject row = items.getJSONObject(i); int id = row.getInt("id");
                String date = OffsetDateTime.parse(row.getString("local_datetime")).format(DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT).withLocale(locale()));
                text(date + " (UTC" + row.getString("local_datetime").substring(row.getString("local_datetime").length() - 6) + ") · " + t("quantity_count", number(row.getInt("quantity"))) + " · " + money(row.getDouble("cost"), row.getString("currency")), 16);
                button(t("delete"), () -> new AlertDialog.Builder(this).setMessage(t("delete_confirm"))
                    .setNegativeButton(t("cancel"), null).setPositiveButton(t("delete"), (dialog, which) -> perform(() -> api("/cigarettes/" + id, "DELETE", null, null), unused -> history())).show());
            }
            historyOffset += items.length();
            if (historyOffset < result.getInt("total")) {
                Button more = button(t("more"), () -> {}); more.setOnClickListener(v -> { if (!busy) { content.removeView(more); loadEntries(); } });
            }
            button(t("back_dashboard"), this::dashboard);
        });
    }
    private Spinner select(String key, ArrayList<String> labels, int selected) {
        TextView caption = text(t(key), 14); Spinner spinner = new Spinner(this);
        spinner.setId(View.generateViewId()); caption.setLabelFor(spinner.getId());
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, labels);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spinner.setAdapter(adapter); spinner.setSelection(Math.max(0, selected)); content.addView(spinner); return spinner;
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
        } catch (Exception error) { status.setText(t("invalid_input")); }
    }
    private void settings() {
        page = "settings"; screen(t("my_preferences")); button(t("back"), this::dashboard);
        perform(() -> new JSONObject().put("prefs", get("/settings")).put("catalog", get("/config")), value -> {
            JSONObject result = (JSONObject)value, prefs = result.getJSONObject("prefs"); catalog = result.getJSONObject("catalog");
            setLanguage(prefs.getString("language"));
            screen(t("my_preferences")); button(t("back"), this::dashboard); button(t("refresh"), this::settings);
            ArrayList<String> languageCodes = new ArrayList<>(), languageLabels = new ArrayList<>();
            JSONArray languages = catalog.getJSONArray("languages");
            for (int i = 0; i < languages.length(); i++) { JSONObject item = languages.getJSONObject(i); languageCodes.add(item.getString("code")); languageLabels.add(item.getString("name")); }
            Spinner languageInput = select("language", languageLabels, languageCodes.indexOf(prefs.getString("language")));
            ArrayList<String> codes = new ArrayList<>(), labels = new ArrayList<>(); JSONArray currencies = catalog.getJSONArray("currencies");
            for (int i = 0; i < currencies.length(); i++) { JSONObject item = currencies.getJSONObject(i); codes.add(item.getString("code")); labels.add(item.getString("code") + " — " + item.getString("name")); }
            Spinner currency = select("currency", labels, codes.indexOf(prefs.getString("currency")));
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
                } catch (Exception e) { status.setText(t("invalid_input")); }
            });
            button(t("back"), this::dashboard);
        });
    }
}
