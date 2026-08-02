# Official Google Requirements Recheck

**Status:** Rechecked against current official sources · **Date checked:** 2026-08-01

This recheck supplements, and does not erase, Phase 4B's dated [Google platform requirements](../phase-4b/google-platform-requirements.md). Only official Google documentation is used.

| Requirement | Current official evidence | Phase 4C consequence |
|---|---|---|
| External audience and Testing publishing status | [Manage App Audience](https://support.google.com/cloud/answer/15549945?hl=en) defines External vs Internal audiences and Testing vs In production | Use External; remain Testing; make no production/verification claim |
| Test-user configuration and cap | The same official audience page limits Testing projects to up to 100 listed test users | Add only `ACCOUNT_A` in Phase 4C; `ACCOUNT_B` remains unlisted unless later authorised |
| Seven-day Testing behaviour | The same official page states test-user authorisations expire seven days after consent, and an offline refresh token also expires | Record the constraint; choose neither soak option; do not consent in Phase 4C |
| Gmail API enablement | [Gmail API Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python) requires a Cloud project and enabling Gmail API | Enable Gmail API in the dedicated project only |
| Calendar/Gmail API enablement generally | [OAuth 2.0 for Web Server Applications](https://developers.google.com/identity/protocols/oauth2/web-server) states each called API must be enabled in the selected project | Enable only Gmail API and Google Calendar API; stop on unexpected billing |
| OAuth consent/Google Auth Platform layout | Current Gmail setup documentation routes configuration through Google Auth Platform Branding, Audience, Data Access, and Clients | Owner uses those current surfaces; stops if an unplanned required value appears |
| Web-application client | [Manage OAuth Clients](https://support.google.com/cloud/answer/15549257?hl=en-uk) and the web-server guide define private web clients with server-held secrets | Create one Web application client; secret stays outside Git/chat and is available in full only at creation |
| Redirect URI/origin rules | The client and web-server guides require exact registered redirect URIs; localhost HTTP is exempt from HTTPS; wildcard characters are prohibited; JavaScript origins are needed only for client-side Google API calls | Register only the two exact localhost server callbacks; no wildcard/alternate/production URI; no speculative JavaScript origin |
| Gmail scope classification | [Choose Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes) classifies `gmail.readonly` and `gmail.compose` as Restricted | Keep both scope strings exact; retain application-level no-send boundary; production verification/security assessment remains future work |
| Calendar scope meaning/classification | [Choose Google Calendar API scopes](https://developers.google.com/workspace/calendar/api/auth) defines `calendar.readonly` as all-calendar read and `calendar.events` as view/edit events; [Sensitive scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification) identifies reading Calendar events as sensitive and says Cloud Console classifies declared scopes | Retain the Phase 4B Sensitive classification, verify the Console grouping before save, and keep LifeFlow's create-only/no-update/delete restrictions |
| Least privilege and partial consent | [OAuth 2.0 Policies](https://developers.google.com/identity/protocols/oauth2/policies) requires only needed scopes and safe handling of partially granted scope sets | Configure only the approved four; LifeFlow continues to persist actual granted scopes and fail closed per missing capability |
| Secret handling | [Manage OAuth Clients](https://support.google.com/cloud/answer/15549257?hl=en-uk) says new client secrets are shown/downloadable in full only at creation and must not be committed or shared insecurely | Owner saves directly to the ignored local secret mechanism; Codex performs presence-only validation |

## Fresh-verification conclusion

The current official requirements remain compatible with the approved Phase 4C design. No requirement authorises consent, connection, token creation, or provider access. The official sources also expose two load-bearing operator checks that must be verified in the live Console before save: the declared scope grouping, and the app remaining in Testing status.
