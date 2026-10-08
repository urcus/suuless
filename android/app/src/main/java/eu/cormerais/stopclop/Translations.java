package eu.cormerais.stopclop;

import android.content.Context;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

/** Catalogs are copied from the web source during the Gradle build. */
final class Translations {
    private final JSONObject messages;
    Translations(Context context, String language) {
        try (InputStream stream = context.getAssets().open("locales/" + language + ".json")) {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            byte[] buffer = new byte[4096]; int n;
            while ((n = stream.read(buffer)) != -1) bytes.write(buffer, 0, n);
            messages = new JSONObject(bytes.toString(StandardCharsets.UTF_8.name()));
        } catch (Exception error) { throw new IllegalStateException("Missing translation catalog: " + language, error); }
    }
    String text(String key, Object... args) {
        String result = messages.optString(key, key);
        for (int index = 0; index < args.length; index++) result = result.replace("{" + index + "}", String.valueOf(args[index]));
        return result;
    }
}
