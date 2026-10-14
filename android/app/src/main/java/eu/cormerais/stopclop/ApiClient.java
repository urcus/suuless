package eu.cormerais.stopclop;

import org.json.JSONObject;
import org.json.JSONArray;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** Shared HTTP transport for the foreground app and the home-screen widget. */
final class ApiClient {
    static final class HttpError extends Exception {
        final int status;
        HttpError(int status, String message) { super(message); this.status=status; }
    }
    static Object request(String server, String token, String language, String path, String method, JSONObject data, String key) throws Exception {
        HttpURLConnection connection=(HttpURLConnection)new URL(server+"/api"+path).openConnection();
        try {
            connection.setConnectTimeout(5000);connection.setReadTimeout(10000);connection.setInstanceFollowRedirects(false);connection.setUseCaches(false);
            connection.setRequestMethod(method);connection.setRequestProperty("Accept-Language",language);
            if(!token.isEmpty())connection.setRequestProperty("Authorization","Bearer "+token);
            if(key!=null)connection.setRequestProperty("Idempotency-Key",key);
            if(data!=null){
                connection.setDoOutput(true);connection.setRequestProperty("Content-Type","application/json");
                try(var stream=connection.getOutputStream()){stream.write(data.toString().getBytes(StandardCharsets.UTF_8));}
            }
            int code=connection.getResponseCode();if(code==204)return new JSONObject();
            String raw;
            try(InputStream stream=code>=400?connection.getErrorStream():connection.getInputStream()){
                if(stream==null)raw="{}";
                else {java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream();byte[] buffer=new byte[4096];int n;
                    while((n=stream.read(buffer))!=-1)bytes.write(buffer,0,n);raw=bytes.toString(StandardCharsets.UTF_8.name());}
            }
            if(code<200||code>=300){
                String message="HTTP "+code;try{message=new JSONObject(raw).optString("error",message);}catch(Exception ignored){}
                throw new HttpError(code,message);
            }
            if(path.split("\\?",2)[0].matches(".*\\.(csv|html)"))return raw;
            return raw.startsWith("[")?new JSONArray(raw):new JSONObject(raw);
        }finally{connection.disconnect();}
    }
}
