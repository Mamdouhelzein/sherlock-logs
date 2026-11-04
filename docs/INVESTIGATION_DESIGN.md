# Investigation workbench

The page helps an administrator move from a collected sign-in to its observed evidence, calibrated detector decision, incident timeline, and retained account history.

Palette: midnight #10141f, slate #1a2131, paper #e8edf8, periwinkle #90b3ff, amber #f1c580, coral #f38f8a. Blue means navigation/context, amber means incomplete coverage, and coral marks a detector flag. Text accompanies every state.

Type: the existing locally hosted IBM Plex Sans for reading and controls. Monospace is reserved for identifiers and model fingerprints. Headings are sentence case, left aligned, with no decorative labels.

Layout: a compact operational strip above a split ledger/evidence pane. The left pane changes between events and grouped incidents; the right pane explains the selected event. On narrow screens the evidence follows the list. Account history is a server-filtered event ledger, not a filter of only the current page.

    Investigation desk                       Refresh
    Worker at last check | Scored | Flagged | Queue
    Coverage notice
    Events / Incidents      Filter and search loaded rows
    Ledger                  Evidence and model decision
    Load older records      Timeline / context / features

Review: retained the internal-dashboard search's data density and row highlighting; discarded its marketing gateway pattern and default fonts. Avoid generic identical KPI cards and decorative charts. The distinctive element is the connected event-to-evidence layout. Motion follows selection only and respects both the workspace motion control and reduced-motion settings.

No sample incident appears in the live app. Empty, pending, missing-context, unavailable, expired, and denied states are explicit. Scores are anomaly measures, not compromise probabilities or causal explanations. Reads remain administrator-only; there are no account promotion, blocking, or incident mutation controls.
