"""Friday is written in US English (13 Nov, from a client's notes: "grey is also the UK spelling, also several
instances of spellings like 'colour'"; the user: "the spellings should all be US not UK"). Every tracked text file: the
app's words, the site, the Mac app, the docs and comments. "Cancelled" isn't checked: it's also Google's event status
and the code's job flags, so the words people read say "canceled" by hand (the sign-in message)."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# British spellings, by kind (15 Nov, the user: "make sure in every piece of text across any piece of friday software
# ... there is no british english ONLY american english"; the first list knew only a dozen words). Words that are
# also American (advise, exercise, promise, revise, dialogue) aren't here.
OUR = (
    "colour behaviour favour honour labour neighbour flavour humour rumour harbour armour vapour savour endeavour odour"
)
OUR += " parlour valour vigour clamour splendour saviour"
ISE = "organis realis recognis prioritis summaris customis optimis minimis maximis apologis categoris"
ISE += " finalis initialis normalis personalis utilis visualis synchronis authoris emphasis memoris specialis"
ISE += " standardis criticis characteris materialis localis serialis sanitis tokenis capitalis digitis"
ISE += " legalis mobilis neutralis rationalis stabilis symbolis harmonis jeopardis patronis penalis"
ISE += " familiaris generalis centralis hospitalis idealis itemis randomis"
UK = sorted(
    {
        w + end
        for w in OUR.split()
        for end in ("", "s", "ed", "ing", "ful", "ite", "ites", "able", "less", "ably", "hood")
    }
    | {"re" + w + end for w in OUR.split() for end in ("", "s", "ed", "ing")}
    | {w + end for w in ISE.split() for end in ("e", "es", "ed", "ing", "er", "ers", "ation", "ations", "able")}
    | set(
        "centre centres centred centring metre metres litre litres theatre theatres fibre fibres calibre "
        "sombre spectre kilometre kilometres manoeuvre manoeuvres analyse analysed analyses analysing "
        "paralyse paralysed catalyse travelled travelling traveller travellers cancelling labelled labelling "
        "unlabelled relabelled modelled modelling signalled signalling fuelled fuelling levelled levelling "
        "totalled totalling counselling counsellor jewellery fulfil fulfils fulfilment enrol enrols enrolment "
        "instalment instalments skilful wilful marvellous focussed focussing benefitted benefitting grey "
        "greys greyed greyish programme programmes catalogue catalogues analogue licence licences defence "
        "offence pretence practise practised practising tyre tyres cheque cheques aluminium plough mould "
        "mouldy sceptical sceptic paediatric encyclopaedia storey storeys judgement judgements "
        "acknowledgement acknowledgements ageing artefact artefacts whilst amongst learnt spelt dreamt "
        "enquiry enquiries enquire kerb aeroplane draught draughts doughnut pyjamas sulphur cosy moustache".split()
    )
)
FOUND = re.compile(r"(?<![A-Za-z])(" + "|".join(UK) + r")(?![A-Za-z])", re.I)
NOT_OURS = re.compile(r"(^|/)(pnpm-lock\.yaml|uv\.lock)$|\.(woff2?|png|jpg|ico|icns|pdf|bundle)$")


def test_no_uk_spellings_in_what_friday_says_or_ships() -> None:
    names = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True).stdout
    found = []
    for name in names.split():
        if NOT_OURS.search(name) or name == "tests/test_us_spelling.py":
            continue
        try:
            text = (ROOT / name).read_text()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if FOUND.search(line):
                found.append(f"{name}:{n}: {FOUND.search(line)[0]}")
    assert not found, "UK spellings (Friday is in US English):\n" + "\n".join(found[:40])


def test_a_canceled_sign_in_says_canceled() -> None:
    assert '"Sign-in canceled."' in (ROOT / "src" / "friday" / "commands" / "connecting.py").read_text()
