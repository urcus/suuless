# SuuLess +1 — English shortcut

[Full iPhone guide](../docs/user-guide/iphone-shortcut.md) · [API documentation](../docs/api/README.md)

Record one cigarette using Apple Shortcuts, then add **SuuLess +1** to your iPhone Home Screen as a button or widget. A connection to your SuuLess server is required. This shortcut does not provide an offline queue or a continuously updated counter.

## Files in this folder

| File | Purpose |
|---|---|
| [SuuLess-Plus-One.shortcut](SuuLess-Plus-One.shortcut) | Signed export intended for import into Apple Shortcuts. |
| [SuuLess-Plus-One-EN.UNSIGNED.shortcut](SuuLess-Plus-One-EN.UNSIGNED.shortcut) | Editable binary plist source; requires signing/export before distribution for installation. |
| [SuuLess-Plus-One-EN.json](SuuLess-Plus-One-EN.json) | Readable workflow source for review and maintenance; not an installable shortcut. |

The signed export contains both setup questions and matches the unsigned/JSON sources for the request and setup parameters. Its signature trust and import behavior have not been validated on an iPhone. The current files still contain the author's server address as a default; replace it with your own before use. See the publication checklist below before distributing these files publicly.

## Before installation

- Open your SuuLess instance in Safari and sign in with an ordinary user account. Administrator accounts cannot record consumption.
- Use HTTPS with a certificate trusted by the phone. A private server requires access through its local network or a suitable VPN.
- In SuuLess, open **Settings & integrations → API keys & sessions**, create a personal key named `iPhone +1`, and copy it immediately. It cannot be displayed again.
- Check your account's time zone and pack price. Entries use the server's current time and your current price; daily totals follow your account's time zone.

Personal API keys grant full account access and expire after 365 days. Use the key rather than your account password or a temporary login session token.

## Install and configure

1. Download **SuuLess-Plus-One.shortcut** as a file. When downloading from a repository, use its raw/download action rather than saving the HTML preview page.
2. Transfer or save it to the iPhone, open it with **Shortcuts**, and inspect the actions before adding it.
3. Answer the two setup questions in order:

   | Question | What to enter |
   |---|---|
   | SuuLess API endpoint | The complete URL, for example `https://suuless.example.com/api/cigarettes`, replacing the example domain with your server. |
   | SuuLess API Key | Your personal key alone, without `Bearer `, quotation marks or extra whitespace. |

4. Check the **Get Contents of URL** action before running: it must target your own server. The shortcut sends your API key to this address.
5. Run once and allow access to your server if iOS asks. Open SuuLess History and verify that exactly one new entry appears. This test records a real cigarette; delete the test entry afterward if appropriate.

The URL must include `https://` and end with `/api/cigarettes`, without a trailing slash. The shortcut does not append that path or validate the address automatically. Setup answers are saved in the shortcut; they are not requested on each button press.

If iOS rejects the file, do not rename the unsigned source and assume it is signed. Use the [manual creation guide](../docs/user-guide/iphone-shortcut.md#2-build-the-shortcut) or obtain a fresh export from Apple Shortcuts.

## Add the Home Screen button or widget

For a widget, open the Home Screen widget gallery, add the small **Shortcuts** widget, then hold it and choose **Edit Widget → SuuLess +1**. For an app-sized icon, use **Add to Home Screen** from the shortcut's menu/details. Labels vary by iOS version; the [illustrated guide](../docs/user-guide/iphone-shortcut.md#4-add-the-home-screen-widget) links Apple's setup instructions.

Depending on permissions and actions, iOS may open Shortcuts or request interaction when you tap the button.

## Request and confirmation behavior

The shortcut sends:

```http
POST /api/cigarettes
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{"quantity":1,"source":"api"}
```

Each successful request records one cigarette. The current notification says **“Request sent. Check SuuLess for the new record.”** It does not check the response ID or confirm that the entry was saved. Network or HTTP errors may stop execution before the notification.

After a timeout or an uncertain result, check History before trying again: the server may already have saved the entry. This shortcut has no automatic retry and sends no idempotency key; another run can create another entry. For a confirmation based on the response ID, follow [Confirm that the entry was saved](../docs/user-guide/iphone-shortcut.md#3-confirm-that-the-entry-was-saved).

For authentication errors, check the key's expiry, revocation and accidental whitespace. For connection errors, check the endpoint, certificate trust and Wi-Fi/VPN access. More cases are covered in [Troubleshooting](../docs/user-guide/iphone-shortcut.md#troubleshooting).

## Change the server or key

Open the shortcut editor and change the URL in **Get Contents of URL** or the key in the first **Text** action. Keep the Authorization header's `Bearer ` prefix and its reference to that Text action. Recheck the destination before testing a new key.

The key is stored in the shortcut. Do not share a configured shortcut file, an iCloud shortcut link or a screenshot containing the key. Revoke an exposed key in SuuLess and replace it in the shortcut.

## Maintain and export

Keep the JSON and unsigned plist sources synchronized. Editing either source does not update the signed export. On a Mac with the Apple Shortcuts CLI, run from this folder:

```sh
shortcuts sign --mode anyone \
  --input SuuLess-Plus-One-EN.UNSIGNED.shortcut \
  --output SuuLess-Plus-One.shortcut
```

Alternatively, edit the shortcut in Apple Shortcuts, verify its setup questions and share/export a fresh file. See [Apple's import-question instructions](https://support.apple.com/en-md/guide/shortcuts/apdf330fd3a0/10.0/ios/27) and [command-line signing instructions](https://support.apple.com/guide/shortcuts-mac/run-shortcuts-from-the-command-line-apd455c82f02/mac).

Before public distribution:

- Replace the author's server address in the URL action and URL question's default answer with `https://suuless.example.com/api/cigarettes` in both sources, then regenerate the signed export.
- Keep a placeholder in the API-key Text action and an empty default answer for its setup question. Remove any personal configuration used for testing.
- Exclude the `__MACOSX/` directory and `._*` metadata files from the distributed archive/repository.
- Inspect the final signed payload for both questions and placeholders; test its import and one request on an iPhone using a demonstration account.

## Validation status

The signed payload was extracted and inspected. Both setup questions target existing parameters; the Bearer variable references the correct Text action; quantity is numeric. The JSON and unsigned sources match, and the extracted request body was accepted by SuuLess on a temporary test database.

Signature trust, setup prompts, notifications and widget execution still require testing on a physical iPhone. No real-device screenshot is included; the full guide contains a configuration schematic.
