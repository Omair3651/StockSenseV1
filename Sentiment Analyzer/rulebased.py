"""
PSX Corporate Announcement Rule-Based Sentiment Analyzer
=========================================================
Analyzes Pakistan Stock Exchange (PSX) corporate announcements
and assigns sentiment labels with confidence scores and category tags.

Labels:  positive | neutral | negative
Output:  label, score (0.0-1.0), category, sub_category, explanation
"""

import re
from dataclasses import dataclass
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class SentimentResult:
    label:        str            # positive | neutral | negative
    score:        float          # confidence 0.0–1.0
    category:     str            # high-level category
    sub_category: str            # detailed sub-category
    explanation:  str            # human-readable reason
    flags:        list           # list of matched rule flags

    def to_dict(self):
        return {
            'label':        self.label,
            'score':        round(self.score, 4),
            'category':     self.category,
            'sub_category': self.sub_category,
            'explanation':  self.explanation,
            'flags':        self.flags,
        }

    def __repr__(self):
        return (f"SentimentResult(label={self.label!r}, score={self.score:.2f}, "
                f"category={self.category!r}, explanation={self.explanation!r})")


# ─────────────────────────────────────────────────────────────────────────────
# Helper patterns (pre-compiled for speed)
# ─────────────────────────────────────────────────────────────────────────────
_P = {
    # ── Positive ─────────────────────────────────────────────────────────────
    'dividend_payment':  re.compile(
        r'(credit of|dispatch of|payment of|disbursement|e-payment|e-credit|'
        r'dispatch\/credit|credit\/dispatch|payment of (final|interim)|'
        r'notice of (dispatch|payment|credit) of).{0,50}'
        r'(dividend|bonus shares?|cash dividend|interim dividend|final dividend)',
        re.I),
    'dividend_generic':  re.compile(
        r'(interim dividend|final dividend|final cash dividend|bonus shares? certificates?|'
        r'dispatch of dividend warrants?|credit of (final|interim|first|second|third))',
        re.I),
    'successful_op':     re.compile(
        r'^successful (commissioning|drilling|workover|settlement|operations?|'
        r'testing|completion|installation|revival)', re.I),
    'production_revival':re.compile(
        r'(discovery of (hydrocarbon|oil|gas)|revives?|restoring|restored|enhanced production|production optimis|'
        r'esp success|production from|farm-in agreement|increases? working interest|'
        r'enhances? production|advances? production|new (oil|gas) well|'
        r'gas discovery|oil discovery|hydrocarbon discovery|new discovery)', re.I),
    'rating_upgrade':    re.compile(
        r'(upgraded?|rating upgraded|rating improved|vis upgraded|pacra upgraded|'
        r'upgrade in (rating|credit))', re.I),
    'rating_affirmed':   re.compile(
        r'(reaffirms?|affirmed?|maintained?).{0,20}(rating|entity rating)', re.I),
    'acquisition_complete': re.compile(
        r'(completion of acquisition|acquisition completed|successfully acquired|'
        r'completes? acquisition|completes? merger|merger completed|'
        r'amalgamation approved|consolidation approved)', re.I),
    'expansion':         re.compile(
        r'(new plant|capacity expansion|new project|expansion project|'
        r'increase in committed expenditure|approval of (new|additional) (project|'
        r'capacity|investment)|new (manufacturing|production) facility|'
        r'signing of agreements? for.{0,30}(block|exploration|project)|'
        r'strategic (partnership|alliance|agreement) with|sbp approval to .{0,30}'
        r'commence due diligence)', re.I),
    'buyback_active':    re.compile(
        r'purchase.{0,10}\(buy.?back\) of [\d,]+ shares|'
        r'buy.?back of [\d,]+ shares|'
        r'completion of.{0,10}buy.?back|'
        r'buy.?back completed', re.I),
    'privatisation_pos': re.compile(
        r'privatisation? (approved|completed|successful)|'
        r'(bid approved|consortium approved).{0,30}privatis', re.I),
    'sbp_approval':      re.compile(
        r'sbp (approval|approved|grants?).{0,30}(merger|acquisition|due diligence|'
        r'amalgamation|licence|license)', re.I),
    'award_win':         re.compile(
        r'(wins?|won|awarded|award for|recognition|achievement|milestone achieved|'
        r'certified|accredited|becomes? (first|largest|leading))', re.I),
    'profit_up':         re.compile(
        r'profit.{0,20}(up|rises?|grew|grows?|jumps?|surges?|increases?|higher|'
        r'beats?|exceeds?|above expectations?|record (high|profit))', re.I),
    'ipo_success':       re.compile(
        r'(oversubscribed|ipo (completed|success|approved)|'
        r'listing (approved|successful|completed))', re.I),

    # ── Negative ─────────────────────────────────────────────────────────────
    'demise':            re.compile(
        r'(sad demise|demise of|obituary|passed away|death of|'
        r'intimation (of|about) (sad )?demise)', re.I),
    'cancellation':      re.compile(
        r'(cancellation of board meeting|board meeting cancelled|'
        r'meeting (cancelled|postponed|rescheduled))', re.I),
    'revocation':        re.compile(
        r'\bREVOKED\b|revocation of|'
        r'(withdrawal of|withdrawn?) public announcement|'
        r'withdrawal of (offer|bid|intention)', re.I),
    'penalty_fine':      re.compile(
        r'(penalty imposed|penalised?|fined?|fine of rs|'
        r'monetary penalty|regulatory fine|secp.{0,15}penalty)', re.I),
    'loss_reported':     re.compile(
        r'(incurs? (a )?loss|reported loss|net loss of|loss after tax|'
        r'loss before tax|pat: loss|pbt: loss)', re.I),
    'profit_down':       re.compile(
        r'profit.{0,20}(down|falls?|drops?|declines?|plunges?|lower|'
        r'decreased?|reduced?|below expectations?)', re.I),
    'plant_shutdown':    re.compile(
        r'(plant (shutdown|closure|halt)|temporary (shutdown|halt|closure)|'
        r'suspension of (operations?|production)|'
        r'unit (shutdown|shut down)|production halted)', re.I),
    'deal_termination':  re.compile(
        r'(terminat.{0,20}(agreement|deal|contract|spa|mou|acquisition)|'
        r'abandon.{0,20}(deal|agreement|acquisition|merger)|'
        r'scrapped?|calls? off|deal (cancelled|failed|collapsed))', re.I),
    'winding_up':        re.compile(
        r'(winding up|liquidation|voluntar.{0,15}liquidat|'
        r'dissolution of|termination of.{0,20}(branch|subsidiary))', re.I),
    'loss_certificates': re.compile(r'loss of (share )?certificates?', re.I),
    'rating_downgrade':  re.compile(
        r'(downgraded?|rating downgraded|rating lowered|negative outlook|'
        r'rating watch negative)', re.I),
    'de_scheduling':     re.compile(
        r'(de.?scheduling|de.?listed|cancellation of (banking )?licen[cs]e|'
        r'banking licen[cs]e cancelled)', re.I),
    'sbp_fine':          re.compile(
        r'sbp.{0,30}(fine|penalt|impose)', re.I),
    'secp_action':       re.compile(
        r'secp.{0,30}(show cause|penalt|fine|action|notice issued)', re.I),
    'operational_issue': re.compile(
        r'(force majeure|circular debt|supply (shortage|disruption)|'
        r'fuel shortage|gas curtailment|receivables.{0,20}mount|'
        r'financial (distress|crisis|difficulties))', re.I),

    # ── Neutral ───────────────────────────────────────────────────────────────
    'board_meeting_notice': re.compile(
        r'(board (of directors )?meeting|notice of board meeting)', re.I),
    'agm_egm_notice':    re.compile(
        r'(annual general meeting|extra.?ordinary general meeting|'
        r'\bagm\b|\begm\b|notice of (annual|extraordinary))', re.I),
    'director_disclosure': re.compile(
        r'(disclosure of interest|disclosure by (a |relevant )?director|'
        r'disclosure of (shareholding|interest).{0,30}(director|ceo|executive)|'
        r'substantial shareholders?)', re.I),
    'financial_results_filing': re.compile(
        r'(financial results? for|quarterly (financial )?results?|'
        r'annual (financial )?results?|half.?year(ly)? results?|'
        r'nine.?months? results?|unaudited (financial|results)|'
        r'audited (financial|results))', re.I),
    'financial_report_transmission': re.compile(
        r'(transmission of (annual|quarterly|half.?year) report|'
        r'annual report for|quarterly report for)', re.I),
    'appointment_neutral': re.compile(
        r'(appointment of|reappointment of|nomination of).{0,30}'
        r'(director|ceo|cfo|md|managing director|chairman)', re.I),
    'resignation_neutral': re.compile(
        r'(resignation of|retired?|retiring).{0,30}'
        r'(director|ceo|cfo|md|managing director|chairman)', re.I),
    'book_closure':      re.compile(r'book closure', re.I),
    'rights_issue':      re.compile(
        r'(rights? (issue|shares?|offering)|progress report of rights)', re.I),
    'sukuk_tfc':         re.compile(
        r'(sukuk|term finance certificates?|tfc|'
        r'profit payment.{0,20}(bond|sukuk|tfc)|'
        r'coupon payment|principal payment)', re.I),
    'stock_split_neutral': re.compile(
        r'(sub.?division of shares|stock split|share split|'
        r'credit of (ordinary )?shares.{0,20}pursuant to)', re.I),
    'corporate_briefing': re.compile(
        r'(corporate briefing|investor briefing|analyst briefing|'
        r'cbs|corporate briefing session)', re.I),
    'ballot_voting':     re.compile(
        r'(ballot paper|postal ballot|voting through post|'
        r'e.?voting|electronic voting facility)', re.I),
    'newspaper_notice':  re.compile(
        r'(newspaper (cuttings?|advertisement|clipping)|'
        r'(prior to|text of) publication|published in (newspaper|print))', re.I),
    'bare_company_name': re.compile(
        r'^[a-z\s]*(limited|ltd\.?)$', re.I),
    'acquisition_announcement': re.compile(
        r'(public announcement of (offer|intention) to acquire|'
        r'offer to acquire shares|joint control of|'
        r'extension in timeline for public announcement)', re.I),
    'secp_approval_neutral': re.compile(
        r'secp (approval|approved|approved amendments|approves?).{0,30}'
        r'(scheme|amendments?|option scheme|restructuring)', re.I),
    'agreement_signed': re.compile(
        r'(signing of (mou|agreement|mou|memorandum)|'
        r'strategic.{0,15}partnership (with|signed)|'
        r'mou (signed|executed))', re.I),
    'provisional_award': re.compile(
        r'provisional award', re.I),
    'buyback_notice':    re.compile(
        r'(notice of buy.?back|buy.?back (programme|initiated|announced|report)|'
        r'final report on buy.?back|closure of (purchase|buy.?back) period)', re.I),
    'loss_cert_admin':   re.compile(r'loss of (share )?certificates?', re.I),


    'ceo_cfo_change': re.compile(
        r'(change of (chief executive|ceo|cfo|chief financial|company secretary|md|managing director)|'
        r'change in (chief executive|ceo|cfo|chief financial|company secretary)|'
        r'(appointment|resignation|retirement|reappointment|tenure completion) of '
        r'(chief executive|ceo|cfo|chief financial|company secretary|managing director|chairman))', re.I),
    'half_yearly_report': re.compile(
        r'(half.?year(ly)? report|transmission of.{0,30}(half.?year|quarterly|annual) report|'
        r'interim (financial|condensed) (report|accounts)|'
        r'transmission of.{0,30}(period|ended|december|june|september|march))', re.I),
    'meeting_logistics': re.compile(
        r'(change (in|of) (time|date|venue) of.{0,20}meeting|'
        r'postponement of (board|agm|egm) meeting|'
        r'meeting of the board of directors and closed period|'
        r'closed period for|trading halt)', re.I),
    'secretarial': re.compile(
        r'(auditors? (certificate|report|opinion|appointment|change)|'
        r'change of (company secretary|auditor|registrar|transfer agent)|'
        r'appointment of (auditor|registrar|company secretary)|'
        r'statutory (compliance|notice|obligation)|'
        r'tenure completion of (chairman|director))', re.I),
    'dividend_publication': re.compile(
        r'publication of.{0,40}(dividend|bonus shares?|cash dividend|interim dividend)', re.I),
    'election_directors': re.compile(r'(election of directors?|notice of election)', re.I),
    'accounts_transmission': re.compile(
        r'(transmission of|submission of).{0,30}(financial statements?|accounts?|'
        r'half.?year(ly)? (accounts?|statements?|financial)|condensed (interim|financial)|'
        r'quarterly (financial statements?|accounts?|report)|annual (accounts?|statements?))', re.I),
    'financial_statements': re.compile(
        r'(financial statements? for|half.?year(ly)? (accounts?|results?|statements?)|'
        r'condensed (interim|financial) (statements?|results?|accounts?)|'
        r'(interim|unaudited) financial statements?|half year (ended|results?|accounts?))', re.I),
    'material_info_neutral': re.compile(
        r'(material information|enquiry on news|clarification (regarding|of|on)|'
        r'response to (media|news|inquiry)|clarification in respect)', re.I),
    'director_change': re.compile(
        r'(change of (alternate|independent|non.?executive|company) director|'
        r'alternate director|independent director|non.?executive director|'
        r'change in board|addition to board)', re.I),
    'shariah_disclosure': re.compile(
        r'(shariah|sharia).{0,30}(disclosure|compliance|report|certificate|review)', re.I),
    'dividend_admin': re.compile(
        r'(withholding of dividend|unclaimed dividend|undelivered (bonus|dividend|shares?)|'
        r'uncollected (dividend|shares?)|cnic.{0,20}dividend)', re.I),
    'general_admin': re.compile(
        r'(notice of|publication of (notice|newspaper)|prior to publication|'
        r'text of (advertisement|notice)|newspaper (advertisement|publication|cuttings?))', re.I),
    'settlement': re.compile(r'settlement with.{0,50}(limited|company|pvt|private)', re.I),
    'production_test': re.compile(r'(tests?.{0,20}well|production (enhancement|from)|'
        r'(kal|nashpa|sui|baragzai|dars|kunnar).{0,15}(field|well|block|test))', re.I),
    'interim_accounts': re.compile(
        r'(condensed interim|interim (financial|condensed)|half.?yearly accounts?|'
        r'(first|second|third|fourth) quarter (ended|results?|accounts?))', re.I),
    'misc_admin':        re.compile(
        r'(change of (registered office|address)|'
        r'change in (company name|name of company)|'
        r'alteration of (memorandum|articles)|'
        r'amalgamation scheme|scheme of arrangement|court order|'
        r'unclaimed dividend|undelivered (bonus|shares)|'
        r'withholding of dividend|cnic|iban)', re.I),
}


# ─────────────────────────────────────────────────────────────────────────────
def analyze(title: str, symbol: str = '') -> SentimentResult:
    """
    Analyze a PSX corporate announcement title and return a SentimentResult.

    Args:
        title:  The announcement title string from PSX filing
        symbol: Optional ticker symbol (e.g. 'OGDC') for context

    Returns:
        SentimentResult with label, score, category, sub_category, explanation
    """
    t  = title.strip()
    tl = t.lower()
    flags = []

    # ── EMPTY / BARE COMPANY NAME ─────────────────────────────────────────────
    if not t or len(t) < 3:
        return SentimentResult('neutral', 0.60, 'Admin', 'empty_title',
                               'Empty or missing title', [])

    if _P['bare_company_name'].match(t.strip()) and len(t.strip()) < 50:
        return SentimentResult('neutral', 0.70, 'Admin', 'bare_company_name',
                               'Title contains only company name — no sentiment signal', ['bare_company_name'])

    # ════════════════════════════════════════════════════════════════════════
    # NEGATIVE RULES  (check first — negative events need priority)
    # ════════════════════════════════════════════════════════════════════════

    # Death / demise — always negative, high confidence
    if _P['demise'].search(t):
        flags.append('demise')
        return SentimentResult(
            'negative', 0.99, 'Corporate Event', 'demise_notification',
            'Announcement of death/demise of board member or director', flags)

    # Licence cancellation / de-scheduling
    if _P['de_scheduling'].search(t):
        flags.append('de_scheduling')
        return SentimentResult(
            'negative', 0.97, 'Regulatory', 'licence_cancellation',
            'Cancellation or de-scheduling of banking licence or regulatory registration', flags)

    # Deal termination / abandonment
    if _P['deal_termination'].search(t):
        flags.append('deal_termination')
        return SentimentResult(
            'negative', 0.95, 'Corporate Action', 'deal_termination',
            'Termination or abandonment of deal, agreement, or acquisition', flags)

    # Penalty / fine
    if _P['penalty_fine'].search(t) or _P['sbp_fine'].search(t) or _P['secp_action'].search(t):
        flags.append('penalty')
        return SentimentResult(
            'negative', 0.93, 'Regulatory', 'penalty_fine',
            'Regulatory penalty or fine imposed on the company', flags)

    # Loss reported
    if _P['loss_reported'].search(t):
        flags.append('loss_reported')
        return SentimentResult(
            'negative', 0.92, 'Financial', 'loss_reported',
            'Company reports a net loss', flags)

    # Profit decline
    if _P['profit_down'].search(t):
        flags.append('profit_down')
        return SentimentResult(
            'negative', 0.90, 'Financial', 'profit_decline',
            'Company reports declining profit or earnings', flags)

    # Plant shutdown / operational halt
    if _P['plant_shutdown'].search(t):
        flags.append('plant_shutdown')
        return SentimentResult(
            'negative', 0.88, 'Operations', 'production_halt',
            'Plant shutdown, production halt or temporary closure announced', flags)

    # Winding up / liquidation
    if _P['winding_up'].search(t):
        # "voluntary winding up" of a subsidiary — less severe than full company
        score = 0.85 if re.search(r'subsidiary|branch|associated', tl) else 0.95
        flags.append('winding_up')
        return SentimentResult(
            'negative', score, 'Corporate Action', 'winding_up_liquidation',
            'Winding up, liquidation or dissolution of company or entity', flags)

    # Credit rating downgrade
    if _P['rating_downgrade'].search(t):
        flags.append('rating_downgrade')
        return SentimentResult(
            'negative', 0.95, 'Regulatory', 'rating_downgrade',
            'Credit rating downgraded or negative outlook assigned', flags)

    # Board meeting cancellation
    if _P['cancellation'].search(t):
        flags.append('cancellation')
        return SentimentResult(
            'negative', 0.88, 'Corporate Event', 'meeting_cancellation',
            'Board meeting or corporate event cancelled', flags)

    # Operational issues (circular debt, supply shortage, etc.)
    if _P['operational_issue'].search(t):
        flags.append('operational_issue')
        return SentimentResult(
            'negative', 0.82, 'Operations', 'operational_difficulty',
            'Operational difficulty — circular debt, supply disruption, or financial distress', flags)

    # ════════════════════════════════════════════════════════════════════════
    # POSITIVE RULES
    # ════════════════════════════════════════════════════════════════════════

    # Dividend payment (credit/dispatch) — clearly positive for investors
    if _P['dividend_payment'].search(t) or _P['dividend_generic'].search(t):
        flags.append('dividend_payment')
        # Check if REVOKED
        if _P['revocation'].search(t):
            flags.append('revoked')
            return SentimentResult(
                'negative', 0.92, 'Corporate Action', 'dividend_revoked',
                'Dividend payment announcement was revoked', flags)
        return SentimentResult(
            'positive', 0.97, 'Shareholder Returns', 'dividend_payment',
            'Dividend or bonus share credited / dispatched to shareholders', flags)

    # Successful operations (drilling, commissioning, workover)
    if _P['successful_op'].search(t):
        flags.append('successful_op')
        return SentimentResult(
            'positive', 0.96, 'Operations', 'successful_operation',
            'Successful completion of operational milestone', flags)

    # Production enhancement / revival / discovery
    if _P['production_revival'].search(t):
        flags.append('production_revival')
        # Discovery is more positive than revival
        score = 0.97 if re.search(r'discovery|discovered|hydrocarbon|new (oil|gas)|discovery of hydrocarbon|discovery of (oil|gas)', tl) else 0.93
        return SentimentResult(
            'positive', score, 'Operations', 'production_positive',
            'Positive operational event — production revival, enhancement, or new discovery', flags)

    # Credit rating upgrade
    if _P['rating_upgrade'].search(t):
        flags.append('rating_upgrade')
        return SentimentResult(
            'positive', 0.96, 'Regulatory', 'rating_upgrade',
            'Credit or entity rating upgraded by rating agency', flags)

    # Rating affirmed (mildly positive — stable)
    if _P['rating_affirmed'].search(t):
        flags.append('rating_affirmed')
        return SentimentResult(
            'positive', 0.80, 'Regulatory', 'rating_affirmed',
            'Credit rating reaffirmed — company creditworthiness maintained', flags)

    # Acquisition completed
    if _P['acquisition_complete'].search(t):
        flags.append('acquisition_complete')
        return SentimentResult(
            'positive', 0.92, 'Corporate Action', 'acquisition_completed',
            'Acquisition or merger successfully completed', flags)

    # Expansion / new project / committed expenditure
    if _P['expansion'].search(t):
        flags.append('expansion')
        return SentimentResult(
            'positive', 0.90, 'Corporate Action', 'expansion_investment',
            'Business expansion, new project, or investment approved', flags)

    # Active share buyback
    if _P['buyback_active'].search(t):
        flags.append('buyback_active')
        return SentimentResult(
            'positive', 0.88, 'Shareholder Returns', 'share_buyback',
            'Active share buyback — company repurchasing its own shares', flags)

    # SBP approval for merger / acquisition / due diligence
    if _P['sbp_approval'].search(t):
        flags.append('sbp_approval')
        return SentimentResult(
            'positive', 0.90, 'Regulatory', 'regulatory_approval',
            'SBP grants approval for merger, acquisition, or due diligence', flags)

    # Award / achievement / milestone
    if _P['award_win'].search(t):
        # Narrow it down — avoid false positives
        if re.search(r'(award|win|won|recognition|certified|accredited|milestone achieved|'
                     r'becomes? (first|largest|leading)|record (high|profit|production))', tl):
            flags.append('award_win')
            return SentimentResult(
                'positive', 0.87, 'Corporate Event', 'award_achievement',
                'Company wins award, achieves milestone, or record performance', flags)

    # Profit growth
    if _P['profit_up'].search(t):
        flags.append('profit_up')
        return SentimentResult(
            'positive', 0.91, 'Financial', 'profit_growth',
            'Company reports profit growth or record earnings', flags)

    # IPO / listing success
    if _P['ipo_success'].search(t):
        flags.append('ipo_success')
        return SentimentResult(
            'positive', 0.90, 'Corporate Action', 'ipo_listing',
            'IPO oversubscribed or listing successfully completed', flags)

    # Privatisation approval
    if _P['privatisation_pos'].search(t):
        flags.append('privatisation_pos')
        return SentimentResult(
            'positive', 0.88, 'Corporate Action', 'privatisation',
            'Privatisation approved or bid cleared', flags)

    # ════════════════════════════════════════════════════════════════════════
    # NEUTRAL RULES  (administrative / procedural filings)
    # ════════════════════════════════════════════════════════════════════════

    # Revocation (of any filing) — neutral unless it was a dividend (handled above)
    if _P['revocation'].search(t):
        flags.append('revocation')
        return SentimentResult(
            'neutral', 0.82, 'Admin', 'filing_revoked',
            'Previous filing revoked — usually an administrative correction', flags)

    # Director interest disclosure
    if _P['director_disclosure'].search(t):
        flags.append('director_disclosure')
        return SentimentResult(
            'neutral', 0.99, 'Regulatory Filing', 'director_disclosure',
            'Statutory disclosure of director shareholding interest', flags)

    # Board meeting notice
    if _P['board_meeting_notice'].search(t):
        flags.append('board_meeting')
        return SentimentResult(
            'neutral', 0.98, 'Corporate Event', 'board_meeting_notice',
            'Notice of board of directors meeting', flags)

    # AGM / EGM notice
    if _P['agm_egm_notice'].search(t):
        flags.append('agm_egm')
        return SentimentResult(
            'neutral', 0.98, 'Corporate Event', 'agm_egm_notice',
            'Notice of Annual or Extraordinary General Meeting', flags)

    # Financial results filing (title only — no profit/loss figures)
    if _P['financial_results_filing'].search(t):
        flags.append('financial_results')
        return SentimentResult(
            'neutral', 0.95, 'Regulatory Filing', 'financial_results_filing',
            'Submission of financial results — no sentiment signal in title alone', flags)

    # Annual / quarterly report transmission
    if _P['financial_report_transmission'].search(t):
        flags.append('financial_report')
        return SentimentResult(
            'neutral', 0.97, 'Regulatory Filing', 'report_transmission',
            'Transmission of annual or periodic financial report', flags)

    # Appointment of director / executive
    if _P['appointment_neutral'].search(t):
        flags.append('appointment')
        return SentimentResult(
            'neutral', 0.94, 'Corporate Event', 'appointment',
            'Appointment or reappointment of board member or executive', flags)

    # Resignation of director / executive
    if _P['resignation_neutral'].search(t):
        flags.append('resignation')
        return SentimentResult(
            'neutral', 0.90, 'Corporate Event', 'resignation',
            'Resignation or retirement of board member or executive', flags)

    # Book closure
    if _P['book_closure'].search(t):
        flags.append('book_closure')
        return SentimentResult(
            'neutral', 0.97, 'Admin', 'book_closure',
            'Book closure notice for dividend or entitlement', flags)

    # Rights issue
    if _P['rights_issue'].search(t):
        flags.append('rights_issue')
        return SentimentResult(
            'neutral', 0.90, 'Corporate Action', 'rights_issue',
            'Rights issue announcement or progress report', flags)

    # Sukuk / TFC payments
    if _P['sukuk_tfc'].search(t):
        flags.append('sukuk_tfc')
        return SentimentResult(
            'neutral', 0.93, 'Debt Instrument', 'sukuk_tfc_payment',
            'Scheduled sukuk, TFC, or bond payment notification', flags)

    # Stock split / sub-division
    if _P['stock_split_neutral'].search(t):
        flags.append('stock_split')
        return SentimentResult(
            'neutral', 0.92, 'Corporate Action', 'stock_split',
            'Share sub-division or stock split — neutral corporate restructuring', flags)

    # Corporate briefing
    if _P['corporate_briefing'].search(t):
        flags.append('corporate_briefing')
        return SentimentResult(
            'neutral', 0.95, 'Corporate Event', 'corporate_briefing',
            'Corporate or investor briefing session', flags)

    # Ballot / voting material
    if _P['ballot_voting'].search(t):
        flags.append('ballot_voting')
        return SentimentResult(
            'neutral', 0.97, 'Admin', 'voting_material',
            'AGM/EGM voting material or postal ballot', flags)

    # Newspaper notice / publication
    if _P['newspaper_notice'].search(t):
        flags.append('newspaper_notice')
        return SentimentResult(
            'neutral', 0.92, 'Admin', 'newspaper_publication',
            'Newspaper advertisement or notice publication', flags)

    # Acquisition announcement (not completed — in progress)
    if _P['acquisition_announcement'].search(t):
        flags.append('acquisition_announcement')
        return SentimentResult(
            'neutral', 0.85, 'Corporate Action', 'acquisition_in_progress',
            'Acquisition offer or intention announced — outcome not yet confirmed', flags)

    # SECP approval (neutral regulatory step)
    if _P['secp_approval_neutral'].search(t):
        flags.append('secp_approval')
        return SentimentResult(
            'neutral', 0.88, 'Regulatory', 'secp_regulatory_approval',
            'SECP approval for scheme, amendment, or restructuring', flags)

    # MOU / agreement signed (exploratory — outcome uncertain)
    if _P['agreement_signed'].search(t):
        flags.append('agreement_signed')
        return SentimentResult(
            'neutral', 0.82, 'Corporate Action', 'mou_agreement',
            'MOU or agreement signed — exploratory, outcome not yet determined', flags)

    # Provisional award (not confirmed)
    if _P['provisional_award'].search(t):
        flags.append('provisional_award')
        return SentimentResult(
            'neutral', 0.78, 'Corporate Action', 'provisional_award',
            'Provisional award — subject to confirmation, not yet final', flags)

    # Share buyback (notice/announcement — not active repurchase)
    if _P['buyback_notice'].search(t):
        flags.append('buyback_notice')
        return SentimentResult(
            'neutral', 0.85, 'Corporate Action', 'buyback_notice',
            'Share buyback programme announced or reported — pending execution', flags)

    # Loss of certificates (admin)
    if _P['loss_cert_admin'].search(t):
        flags.append('loss_certificates')
        return SentimentResult(
            'neutral', 0.92, 'Admin', 'lost_share_certificates',
            'Lost share certificates — routine administrative filing', flags)

    # Misc admin (address change, court orders, unclaimed dividends)
    if _P['misc_admin'].search(t):
        flags.append('misc_admin')
        return SentimentResult(
            'neutral', 0.88, 'Admin', 'miscellaneous_admin',
            'Miscellaneous administrative or regulatory filing', flags)

    # CEO / CFO / Executive change
    if _P['ceo_cfo_change'].search(t):
        flags.append('ceo_cfo_change')
        return SentimentResult(
            'neutral', 0.93, 'Corporate Event', 'executive_change',
            'Change, appointment, or resignation of chief executive, CFO, or secretary', flags)

    # Half-yearly / quarterly report transmission
    if _P['half_yearly_report'].search(t):
        flags.append('half_yearly_report')
        return SentimentResult(
            'neutral', 0.94, 'Regulatory Filing', 'accounts_transmission',
            'Transmission or submission of half-yearly or quarterly report', flags)

    # Meeting logistics (time/venue/date change)
    if _P['meeting_logistics'].search(t):
        flags.append('meeting_logistics')
        return SentimentResult(
            'neutral', 0.90, 'Corporate Event', 'meeting_logistics',
            'Change in meeting time, date, or closed period notification', flags)

    # Secretarial / auditor matters
    if _P['secretarial'].search(t):
        flags.append('secretarial')
        return SentimentResult(
            'neutral', 0.91, 'Admin', 'secretarial_matter',
            'Auditor, registrar or company secretary change or statutory compliance', flags)

    # Dividend publication notices
    if _P['dividend_publication'].search(t):
        flags.append('dividend_publication')
        return SentimentResult(
            'positive', 0.90, 'Shareholder Returns', 'dividend_payment',
            'Publication or notice of dividend payment', flags)

    # Election of directors
    if _P['election_directors'].search(t):
        flags.append('election_directors')
        return SentimentResult(
            'neutral', 0.97, 'Corporate Event', 'election_of_directors',
            'Election or re-election of board directors', flags)

    # Accounts / financial statements transmission (not results with figures)
    if _P['accounts_transmission'].search(t) or _P['financial_statements'].search(t) or _P['interim_accounts'].search(t):
        flags.append('accounts_transmission')
        return SentimentResult(
            'neutral', 0.95, 'Regulatory Filing', 'accounts_transmission',
            'Transmission or filing of financial statements or accounts', flags)

    # Material information / media clarification
    if _P['material_info_neutral'].search(t):
        flags.append('material_info')
        return SentimentResult(
            'neutral', 0.88, 'Regulatory Filing', 'material_information',
            'Material information disclosure or media clarification', flags)

    # Director type change (alternate, independent, non-executive)
    if _P['director_change'].search(t):
        flags.append('director_change')
        return SentimentResult(
            'neutral', 0.93, 'Corporate Event', 'director_change',
            'Change of alternate, independent or non-executive director', flags)

    # Shariah disclosure
    if _P['shariah_disclosure'].search(t):
        flags.append('shariah')
        return SentimentResult(
            'neutral', 0.96, 'Regulatory Filing', 'shariah_disclosure',
            'Shariah compliance disclosure or certificate', flags)

    # Dividend admin (withholding, unclaimed)
    if _P['dividend_admin'].search(t):
        flags.append('dividend_admin')
        return SentimentResult(
            'neutral', 0.90, 'Admin', 'dividend_administration',
            'Dividend administration — withholding, unclaimed, or CNIC-related', flags)

    # Settlement with third party
    if _P['settlement'].search(t):
        flags.append('settlement')
        return SentimentResult(
            'positive', 0.84, 'Corporate Action', 'legal_settlement',
            'Settlement reached with counterparty', flags)

    # Production testing / field operations (neutral — outcome not stated)
    if _P['production_test'].search(t):
        flags.append('production_test')
        return SentimentResult(
            'neutral', 0.80, 'Operations', 'production_testing',
            'Well testing or field production update — outcome details not in title', flags)

    # ── FALLBACK ──────────────────────────────────────────────────────────────
    # If no rule fires, return neutral with low confidence
    return SentimentResult(
        'neutral', 0.60, 'Admin', 'unclassified',
        'No matching rule — treated as neutral admin filing', ['unclassified'])


# ─────────────────────────────────────────────────────────────────────────────
# Batch scorer
# ─────────────────────────────────────────────────────────────────────────────
def score_csv(input_path: str, output_path: str,
              title_col: str = 'title', symbol_col: str = 'symbol'):
    """
    Score a CSV of PSX announcements and write results to output CSV.

    Args:
        input_path:  Path to input CSV
        output_path: Path to output CSV
        title_col:   Column name containing announcement title
        symbol_col:  Column name containing ticker symbol (optional)
    """
    import csv as _csv

    with open(input_path, newline='', encoding='utf-8') as f_in:
        reader = _csv.DictReader(f_in)
        original_cols = reader.fieldnames or []
        rows = list(reader)

    new_cols = ['rule_label', 'rule_score', 'rule_category',
                'rule_sub_category', 'rule_explanation', 'rule_flags']

    with open(output_path, 'w', newline='', encoding='utf-8') as f_out:
        writer = _csv.DictWriter(f_out, fieldnames=original_cols + new_cols)
        writer.writeheader()
        for row in rows:
            title  = row.get(title_col, '')
            symbol = row.get(symbol_col, '')
            result = analyze(title, symbol)
            row.update({
                'rule_label':        result.label,
                'rule_score':        round(result.score, 4),
                'rule_category':     result.category,
                'rule_sub_category': result.sub_category,
                'rule_explanation':  result.explanation,
                'rule_flags':        '|'.join(result.flags),
            })
            writer.writerow(row)

    print(f"Scored {len(rows)} announcements → {output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI / demo
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys

    # Run on the announcements CSV if provided
    if len(sys.argv) >= 3:
        score_csv(sys.argv[1], sys.argv[2])
        sys.exit(0)

    # Demo
    test_cases = [
        # Positive
        ("OGDC", "Credit of Final Cash Dividend D-97"),
        ("PPL",  "Successful Commissioning of Jhim East X1 Well in Shah Bandar Block"),
        ("ILP",  "Material Information - VIS Upgraded Entity Ratings of Interloop Limited"),
        ("OGDC", "OGDCL Revives Rajian-11, Heavy Oil Well, Restoring Production"),
        ("PPL",  "Successful Settlement with Midland Oil Company (Iraq) for Block-8, Iraq"),
        ("BAFL", "SBP Approval to Bank Alfalah Limited to commence due diligence on Samba Bank Limited"),
        ("ENGRO","Credit of Second Interim Cash Dividend"),
        ("PPL",  "Discovery of Hydrocarbons from Exploratory Well Baragzai X-01"),
        ("MEBL", "CREDIT OF FINAL CASH DIVIDEND OF MEEZAN BANK LIMITED"),
        # Neutral
        ("FFC",  "Video of First Corporate Briefing (CBS) for Year 2026 - FFC"),
        ("MCB",  "Newspaper Cuttings of Ballot Paper for Voting through Post"),
        ("UBL",  "Disclosure of Interest by a Director CEO, or Executive of a listed company"),
        ("HBL",  "Board Meeting Other Than Financial Results"),
        ("PPL",  "Provisional Award of Four New Blocks"),
        ("FABL", "Faysal Bank Limited"),
        ("FCCL", "FCCL | Fauji Cement Company Limited - Approval of Annual Budget FY 2019-20"),
        ("PAEL", "Financial Results for the Year Ended 31-12-2025"),
        ("MLCF", "MLCF-Notice of Board Meeting 24.02.2026"),
        # Negative
        ("PSO",  "Sad demise of a Board Member"),
        ("MEBL", "Sad Demise of Mr. Basil Y.A.Y.R Albader Director Meezan Bank Ltd."),
        ("MLCF", "MLCF | Maple Leaf Cement Factory Limited Cancellation of Board Meeting"),
        ("MCB",  "De-Scheduling and Cancellation of Banking License of NIB Bank Limited"),
        ("FCCL", "Credit of Final Cash Dividend (D-15) for FY- 2023/24 REVOKED"),
        ("TGL",  "Material Information SAD DEMISE OF MR. TARIQ BAIG MANAGING DIRECTOR"),
        ("SEARL","Intimation of Sad Demise of Director"),
    ]

    print(f"{'Symbol':<8} {'Label':<10} {'Score':<7} {'Category':<25} {'Title'}")
    print("-" * 110)
    for symbol, title in test_cases:
        r = analyze(title, symbol)
        print(f"{symbol:<8} {r.label:<10} {r.score:<7.2f} {r.category:<25} {title[:55]}")