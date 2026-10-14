package eu.cormerais.stopclop;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.File;
import java.io.FileNotFoundException;

/** Read-only access to a single export explicitly granted through Android's share sheet. */
public final class ExportProvider extends ContentProvider {
    @Override public boolean onCreate() { return true; }
    static File file(android.content.Context context, String name) throws FileNotFoundException {
        if(name == null || !name.matches("suuless-[a-f0-9-]+\\.(csv|html)")) throw new FileNotFoundException();
        return new File(new File(context.getCacheDir(), "exports"), name);
    }
    private File resolve(Uri uri) throws FileNotFoundException {
        if(uri.getPathSegments().size()!=1)throw new FileNotFoundException();
        File result=file(getContext(),uri.getLastPathSegment());
        if(!result.isFile())throw new FileNotFoundException();
        return result;
    }
    @Override public String getType(Uri uri) { return uri.getPath()!=null && uri.getPath().endsWith(".csv")?"text/csv":"text/html"; }
    @Override public ParcelFileDescriptor openFile(Uri uri,String mode) throws FileNotFoundException {
        if(!"r".equals(mode))throw new FileNotFoundException("Read only");
        return ParcelFileDescriptor.open(resolve(uri),ParcelFileDescriptor.MODE_READ_ONLY);
    }
    @Override public Cursor query(Uri uri,String[] projection,String selection,String[] args,String order) {
        try {
            File f=resolve(uri);
            String[] columns=projection==null?new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE}:projection;
            MatrixCursor cursor=new MatrixCursor(columns);Object[] values=new Object[columns.length];
            for(int i=0;i<columns.length;i++)values[i]=OpenableColumns.DISPLAY_NAME.equals(columns[i])?f.getName():OpenableColumns.SIZE.equals(columns[i])?f.length():null;
            cursor.addRow(values);return cursor;
        } catch(FileNotFoundException e) { return null; }
    }
    @Override public Uri insert(Uri uri,ContentValues values) { throw new UnsupportedOperationException(); }
    @Override public int update(Uri uri,ContentValues values,String selection,String[] args) { throw new UnsupportedOperationException(); }
    @Override public int delete(Uri uri,String selection,String[] args) { throw new UnsupportedOperationException(); }
}
