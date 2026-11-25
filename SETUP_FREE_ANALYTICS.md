# Free analytics setup (one time, about 30–45 min, phone works)

This replaces Windsor with the platforms' own free APIs. You create the keys once and save them
as **GitHub secrets** in this repo (Settings → Secrets and variables → Actions → New repository secret).
**Never paste a key or token into chat.** Each part works on its own, so you can do them one at a time.

Secret names must match exactly:

| Secret | What it is |
|---|---|
| `GOOGLE_CLIENT_ID` | From Part A step 4 |
| `GOOGLE_CLIENT_SECRET` | From Part A step 4 |
| `YT_REFRESH_TOKEN_AMM` | Part A step 6, signed in as the AMM channel |
| `YT_REFRESH_TOKEN_YUGYOGII` | Part A step 6, signed in as ancientwisdomwanderer@gmail.com (YugYogii) |
| `META_PAGE_TOKEN_MIRA` | Part B step 5, the "Mira Noir" Page token |
| `META_PAGE_TOKEN_YUGYOGI` | Part B step 5, the "YugYogi" Page token |

---

## Part A — YouTube (both channels, one Google project)

1. Open **console.cloud.google.com** (desktop site view on the phone helps). Create a project named `hanuman-analytics`.
2. **APIs & Services → Library**: enable **YouTube Data API v3** and **YouTube Analytics API**.
3. **OAuth consent screen** (Google Auth Platform): User type **External**, app name `Hanuman Analytics`, your email.
   Add yourself and ancientwisdomwanderer@gmail.com as test users. Then press **Publish app** so it is "In production".
   Important: in "Testing" mode the token expires every 7 days. "In production" without verification is fine for your own accounts;
   you'll just see a "Google hasn't verified this app" warning, tap **Advanced → Go to Hanuman Analytics**.
4. **Credentials → Create credentials → OAuth client ID → Web application**.
   Under *Authorized redirect URIs* add exactly: `https://developers.google.com/oauthplayground`
   Save, then copy the **Client ID** and **Client secret** into the two GitHub secrets.
5. Open **developers.google.com/oauthplayground**. Tap the gear ⚙ (top right): tick **Use your own OAuth credentials**, paste the Client ID and secret.
   Set **Access type: Offline**.
6. In "Step 1" type these two scopes in the box (comma or one per line), then **Authorize APIs**:
   `https://www.googleapis.com/auth/youtube.readonly`
   `https://www.googleapis.com/auth/yt-analytics.readonly`
   Sign in as the **AMM** account and pick the **American Money Mechanics** channel when asked. Tap **Exchange authorization code for tokens**.
   Copy the **Refresh token** into the secret `YT_REFRESH_TOKEN_AMM`.
7. Repeat step 6 in a fresh tab (or after **Revoke**/sign-out), signed in as **ancientwisdomwanderer@gmail.com** with the YugYogii channel,
   and save the refresh token as `YT_REFRESH_TOKEN_YUGYOGII`.

These are read-only permissions: they can read stats, not upload, edit or delete anything.

## Part B — Facebook Pages + linked Instagram (Mira Noir, YugYogi)

1. Open **developers.facebook.com** → **My Apps → Create app** → use case **Other** → type **Business** → name `Hanuman Analytics`.
2. Open **developers.facebook.com/tools/explorer** (Graph API Explorer). Choose the app you just made.
3. **User or Page → Get User Access Token**, and add these permissions:
   `pages_show_list, pages_read_engagement, read_insights, instagram_basic, instagram_manage_insights, business_management`
   Generate, approve for both Pages (Mira Noir and YugYogi) and their Instagram accounts.
4. Tap the **ⓘ** next to the token → **Open in Access Token Tool** → **Extend Access Token** (it's at the bottom). Copy the long-lived token
   and paste it back into the Explorer's token box.
5. In the Explorer, run: `me/accounts?fields=name,access_token`
   Each Page in the result has its own `access_token`. That Page token made from a long-lived token does not expire.
   Save the **Mira Noir** one as `META_PAGE_TOKEN_MIRA` and the **YugYogi** one as `META_PAGE_TOKEN_YUGYOGI`.
   (If YugYogii's Instagram is linked to the YugYogi Page as a professional account, its stats come through the same token.)

Read-only again: these permissions read insights and cannot post.

## Part C — Turn it on

GitHub → **Actions → Daily analytics → Run workflow**. In about a minute `data/analytics/latest.md` appears.
After that it runs by itself every day at 07:47 IST, before the 08:13 huddle. It uses about 1 minute of your
2,000 free Actions minutes a day (about 30 a month).

If something fails, the summary file says which part and the huddle falls back to Windsor or FavStash for it.

## Part D — Buffer (YugYogii publishing, free)

1. Sign up free at **buffer.com** and connect YugYogii's **YouTube**, **Instagram** and **Facebook Page** (that is exactly the 3 free channels).
2. In Claude, connect the **Buffer** connector (Settings → Connectors) so Mahadev's Publisher can queue posts.
   Free plan: 10 queued posts per channel at a time, refilled as they publish. Note Buffer's lifetime limit of 8 channel connections per network
   on the free plan, so don't connect and disconnect accounts casually.
3. Mahadev only queues a Short after your approval; nothing goes live without it.
