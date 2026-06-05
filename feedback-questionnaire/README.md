# Car Race Beta Feedback Questionnaire

Standalone Google Apps Script questionnaire for beta user feedback.

This is separate from the game frontend. It creates a Google Apps Script web app that writes responses into a Google Sheet.

## Files

- `Code.gs`: Apps Script backend. Creates/updates the `Feedback` sheet and stores submissions.
- `Index.html`: Web questionnaire UI shown to beta users.

## Setup

1. Create a new Google Sheet.
2. Rename it if you want, for example `Car Race Beta Feedback`.
3. In the Sheet, open `Extensions` -> `Apps Script`.
4. Replace the default `Code.gs` content with the content from `Code.gs`.
5. Add a new HTML file named exactly `Index`.
6. Paste the content from `Index.html` into that file.
7. Click `Deploy` -> `New deployment`.
8. Select type `Web app`.
9. Set `Execute as` to `Me`.
10. Set `Who has access` to `Anyone with the link`.
11. Click `Deploy`.
12. Copy the web app URL and send it to your beta testers.

## Questions Included

- Required beta tester name.
- Controller connection ease.
- Correct car pairing.
- Smoothness / lag.
- Control responsiveness.
- Lobby instruction clarity.
- Race rules/checkpoint clarity.
- Favorite race mode.
- Graphics rating.
- Biggest problem.
- Would play again.
- Overall rating.
- First improvement priority.
- Optional comment.

## Notes

- The first submission creates the `Feedback` sheet headers automatically.
- Comments are optional.
- All multiple-choice questions are required.
- If you edit question field names in `Index.html`, update `Code.gs` too.
