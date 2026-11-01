package ru.uralia.admin;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;

/** URALIA admin panel as a full-screen app: a WebView over the server's /admin page. No secrets inside: the admin
 *  token is typed in the panel itself (and remembered by the page only if «Запомнить» is ticked). */
public class MainActivity extends Activity {
    static final String DEFAULT_URL = "http://144.31.254.99:8000/admin";
    static final int PICK = 41;
    WebView web;
    ValueCallback<Uri[]> pending;
    SharedPreferences prefs;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        prefs = getSharedPreferences("admin", MODE_PRIVATE);
        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#0b1416"));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(false);
        s.setMediaPlaybackRequiresUserGesture(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setBuiltInZoomControls(true);
        s.setDisplayZoomControls(false);
        s.setUserAgentString(s.getUserAgentString() + " UraliaAdmin/1.0");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                Uri base = Uri.parse(url());
                if (u.getHost() != null && u.getHost().equals(base.getHost())) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception e) { /* no browser */ }
                return true;  // other sites open in the browser
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
                if (r.isForMainFrame()) askServer("Не удалось открыть админку: " + e.getDescription());
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override  // <input type="file">: art, 3D models and APK uploads in the panel
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> cb, FileChooserParams p) {
                if (pending != null) pending.onReceiveValue(null);
                pending = cb;
                Intent i = new Intent(Intent.ACTION_GET_CONTENT);
                i.addCategory(Intent.CATEGORY_OPENABLE);
                i.setType("*/*");
                i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, p.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);
                try {
                    startActivityForResult(Intent.createChooser(i, "Выберите файл"), PICK);
                } catch (Exception e) {
                    pending = null;
                    return false;
                }
                return true;
            }
        });
        setContentView(web);
        immersive();
        if (b != null) web.restoreState(b); else web.loadUrl(url());
    }

    String url() { return prefs.getString("url", DEFAULT_URL); }

    void immersive() {
        if (Build.VERSION.SDK_INT >= 30) {
            getWindow().setDecorFitsSystemWindows(false);
            WindowInsetsController c = getWindow().getInsetsController();
            if (c != null) {
                c.hide(WindowInsets.Type.statusBars() | WindowInsets.Type.navigationBars());
                c.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
            }
        } else {
            getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                | View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        }
    }

    @Override
    public void onWindowFocusChanged(boolean f) {
        super.onWindowFocusChanged(f);
        if (f) immersive();
    }

    void askServer(String msg) {
        final EditText e = new EditText(this);
        e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        e.setText(url());
        new AlertDialog.Builder(this).setTitle("Адрес админки").setMessage(msg).setView(e)
            .setPositiveButton("Открыть", (d, w) -> {
                String u = e.getText().toString().trim();
                if (!u.startsWith("http")) u = "http://" + u;
                prefs.edit().putString("url", u).apply();
                web.loadUrl(u);
            })
            .setNeutralButton("По умолчанию", (d, w) -> {
                prefs.edit().remove("url").apply();
                web.loadUrl(DEFAULT_URL);
            })
            .setNegativeButton("Отмена", null).show();
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) { web.goBack(); return; }
        new AlertDialog.Builder(this).setTitle("Уралия Админ")
            .setItems(new String[]{"Обновить страницу", "Сменить адрес сервера", "Выйти из приложения"}, (d, w) -> {
                if (w == 0) web.reload();
                else if (w == 1) askServer("Например: http://144.31.254.99:8000/admin");
                else finish();
            }).show();
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        if (req != PICK || pending == null) { super.onActivityResult(req, res, data); return; }
        Uri[] out = null;
        if (res == RESULT_OK && data != null) {
            if (data.getClipData() != null) {
                out = new Uri[data.getClipData().getItemCount()];
                for (int i = 0; i < out.length; i++) out[i] = data.getClipData().getItemAt(i).getUri();
            } else if (data.getData() != null) {
                out = new Uri[]{data.getData()};
            }
        }
        pending.onReceiveValue(out);
        pending = null;
    }

    @Override
    protected void onSaveInstanceState(Bundle b) {
        super.onSaveInstanceState(b);
        web.saveState(b);
    }
}
