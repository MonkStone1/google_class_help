import { LifeBuoy, MessageSquarePlus } from "lucide-react";
import { Link } from "react-router-dom";

import { useI18n } from "../shared/i18n/index.ts";

/**
 * The Feedback entry page (ADR-0035).
 *
 * Two cards, not a form: "report something" and "read what I reported" are
 * different intents, and dropping a visitor straight into the editor makes the
 * second one unreachable by accident. Each card explains what it leads to, in
 * the reader's own language — a bare "Create" says nothing about whether the
 * ticket can be followed afterwards.
 */
export function FeedbackHome() {
    const { t } = useI18n();
    return (
        <div className="page">
            <div className="page-header">
                <div>
                    <h1>{t("feedback.title")}</h1>
                    <div className="page-subtitle">
                        {t("feedback.subtitle")}
                    </div>
                </div>
            </div>

            <div className="feedback-choices">
                <Link to="/feedback/new" className="card feedback-choice">
                    <div className="feedback-choice-icon">
                        <MessageSquarePlus size={20} />
                    </div>
                    <div className="feedback-choice-body">
                        <h2>{t("feedback.createTitle")}</h2>
                        <p>{t("feedback.createText")}</p>
                    </div>
                </Link>

                <Link to="/feedback/tickets" className="card feedback-choice">
                    <div className="feedback-choice-icon">
                        <LifeBuoy size={20} />
                    </div>
                    <div className="feedback-choice-body">
                        <h2>{t("feedback.mineTitle")}</h2>
                        <p>{t("feedback.mineText")}</p>
                    </div>
                </Link>
            </div>

            {/*
              No "report a problem — the answer will appear here" note here
              (п.1). It repeated what the "Create a ticket" card directly above
              already says (`feedback.createText`: "…you will be able to read the
              answer here"), so the same sentence appeared twice on one screen and
              the second copy read as a stray caption under the cards.

              The hint is NOT lost: `feedback.emptyHint` still renders as the
              subtitle of the EMPTY state of "My tickets", which is the one place
              where a user with no tickets has not been told what to do yet.
              Nothing else is listed here either — the list has its own route, so a
              reload of /feedback never shows a stale conversation.
            */}
        </div>
    );
}
