"""Text artifact intent and payload contracts, independent of capability dispatch.

Recognizes explicitly scoped output declarations and selects substantive payloads.
It never writes files, calls a provider, supplies missing intent or closes work.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional
from fruth_core.transports import text_artifact_content_is_materializer_instruction_echo


TEXT_ARTIFACT_EXTENSIONS = {
    'txt',
    'md',
    'markdown',
    'html',
    'htm',
    'css',
    'js',
    'mjs',
    'cjs',
    'ts',
    'tsx',
    'jsx',
    'json',
    'yaml',
    'yml',
    'xml',
    'csv',
    'svg',
    'py',
    'sh',
    'sql',
}


_TEXT_ARTIFACT_EXTENSION_RE = re.compile(
    r'(?P<name>[A-Za-z0-9][A-Za-z0-9._-]{0,80})\.(?P<ext>'
    + '|'.join(sorted(TEXT_ARTIFACT_EXTENSIONS, key=len, reverse=True))
    + r')\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_FILE_CUE_RE = re.compile(
    r'\b('
    r'file|files|artifact|artifacts|artefact|artefacts|artefakt|artefakte|datei|dateien|'
    r'document|documents|dokument|dokumente|export|download|downloadable|'
    r'save|saved|speicher|speichere|persist|persistiere|'
    r'materialize|materialized|materialise|materialised|materialisiere|materialisieren|materialisiert|'
    r'write\s+to|as\s+a\s+file|als\s+datei'
    r')\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_ACTION_CUE_RE = re.compile(
    r'\b('
    r'create|generate|make|write|produce|return|provide|build|emit|design|draft|'
    r'change|modify|update|edit|revise|alter|save|store|materialize|materialise|'
    r'erzeuge|erstelle|generiere|schreibe|gib|liefere|bau(?:e|en)?|'
    r'entwirf|entwerfe|entwerfen|gestalte|gestalten|'
    r'aendere|ändere|veraendere|verändere|anpassen|passe|speichere|'
    r'materialisiere|materialisieren'
    r')\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_SOURCE_EDIT_CUE_RE = re.compile(
    r'\b('
    r'change|modify|update|edit|revise|alter|replace|'
    r'add|append|insert|include|remove|delete|section|'
    r'style|restyle|color|colour|font|fix|adjust|tweak|'
    r'aendere|ändere|veraendere|verändere|anpassen|passe|ersetze|'
    r'fuege|füge|hinzufuegen|hinzufügen|entferne|loesche|lösche|abschnitt|'
    r'farbe|schrift|rot|red'
    r')\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_SOURCE_EDIT_ACTION_RE = re.compile(
    r'\b('
    r'change|modify|update|edit|revise|alter|replace|'
    r'add|append|insert|include|remove|delete|style|restyle|color|colour|fix|adjust|tweak|'
    r'aendere|ändere|veraendere|verändere|aktualisiere|anpassen|passe|ersetze|'
    r'fuege|füge|hinzufuegen|hinzufügen|entferne|loesche|lösche|'
    r'gestalte|korrigiere|repariere'
    r')\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_SOURCE_EDIT_NEXT_DIRECTIVE_RE = re.compile(
    r'\b('
    r'change|modify|update|edit|revise|alter|replace|add|append|insert|include|remove|delete|'
    r'style|restyle|color|colour|fix|adjust|tweak|'
    r'create|generate|make|write|produce|return|provide|build|emit|save|materialize|materialise|'
    r'transcribe|analyse|analyze|preserve|'
    r'aendere|ändere|veraendere|verändere|aktualisiere|anpassen|passe|ersetze|'
    r'fuege|füge|hinzufuegen|hinzufügen|entferne|loesche|lösche|gestalte|korrigiere|repariere|'
    r'erzeuge|erstelle|generiere|schreibe|gib|liefere|baue|speichere|materialisiere|'
    r'transkribiere|analysiere|bewahre'
    r')\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_SOURCE_EDIT_CLAUSE_RE = re.compile(r'[^.;:!?\n]+')


_TEXT_ARTIFACT_SOURCE_EDIT_EXPLICIT_SOURCE_RE = re.compile(
    r'\b(?:'
    r'(?:(?:this|that|the|selected|current|existing|attached|uploaded|provided|opened|updated)\s+){1,3}'
    r'(?:file|document|artifact|artefact|source|text|page|checklist|readme)|'
    r'(?:(?:diese|dieses|diesen|dieser|die|das|den|ausgewahlte|ausgewählte|aktuelle|'
    r'bestehende|angehangte|angehängte|hochgeladene|bereitgestellte|geoffnete|geöffnete)\s+){1,3}'
    r'(?:datei|dokument|artefakt|quelle|text|seite|checkliste)'
    r')\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_SOURCE_EDIT_DIRECT_PRONOUN_RE = re.compile(
    r'^\s*(?:(?:please|bitte)\s+)?(?:it|this|that|these|those|dies|diese|dieses|diesen|ihn|sie|es)\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_SOURCE_EDIT_COMPETING_TARGET_RE = re.compile(
    r'\b(?:'
    r'audio[\w-]*|recording|voice|sound|speech|clip|track|'
    r'image[\w-]*|picture|photo|video|visual|'
    r'aufnahme|stimme|tonspur|sprachfassung|'
    r'bild[\w-]*|foto[\w-]*|video[\w-]*|'
    r'graph|subgraph|branch|route|model|tool|workflow|pipeline|node|'
    r'graph[\w-]*|teilgraph|zweig|route|modell|werkzeug|arbeitsablauf|knoten'
    r')\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_SOURCE_EDIT_JSON_TARGET_RE = re.compile(
    r'\bjson\s*(?:[-–—]\s*)?(?:object|objekt|response|antwort|output|ausgabe)\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_SOURCE_EDIT_QUALIFIED_JSON_RESPONSE_TARGET_RE = re.compile(
    r'\b(?:new|final|resulting|response|output|neu(?:e|en|em|er|es)?|'
    r'final(?:e|en|em|er|es)?|abschliessend(?:e|en|em|er|es)?|'
    r'abschließend(?:e|en|em|er|es)?)\s+'
    r'json\s*(?:[-–—]\s*)?(?:object|objekt|response|antwort|output|ausgabe)?\b|'
    r'\bjson\s*(?:[-–—]\s*)?(?:response|antwort|output|ausgabe)\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_SOURCE_EDIT_COMMON_CONTENT_RE = re.compile(
    r'\b(?:'
    r'file|document|artifact|artefact|source|text|content|copy|wording|transcript|'
    r'typo|spelling|grammar|sentence|paragraph|heading|headline|title|section|note|list|table|'
    r'checklist|readme|line|link|url|citation|footer|button|introduction|attribute|caption|label|'
    r'datei|dokument|artefakt|quelle|text|inhalt|wortlaut|transkript|'
    r'tippfehler|rechtschreibung|grammatik|satz|absatz|uberschrift|überschrift|titel|abschnitt|'
    r'notiz|liste|tabelle|checkliste|zeile|link|url|zitat|fusszeile|fußzeile|knopf|'
    r'einleitung|attribut|bildunterschrift|beschriftung'
    r')\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_SOURCE_EDIT_STRONG_CONTENT_RE = re.compile(
    r'\b(?:'
    r'copy|wording|typo|spelling|grammar|sentence|paragraph|heading|headline|title|section|note|'
    r'list|table|checklist|readme|line|link|url|citation|footer|button|introduction|attribute|'
    r'caption|label|wortlaut|tippfehler|rechtschreibung|grammatik|satz|absatz|uberschrift|'
    r'überschrift|titel|abschnitt|notiz|liste|tabelle|checkliste|zeile|zitat|fusszeile|fußzeile|'
    r'knopf|einleitung|attribut|bildunterschrift|beschriftung'
    r')\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_SOURCE_EDIT_COMPOUND_CONTENT_RE = re.compile(
    r'\b(?:audio[\w-]*|image[\w-]*|video[\w-]*|model|graph|route|tool|'
    r'bild[\w-]*|modell|route|werkzeug)\s+'
    r'(?:url|link|field|key|value|property|attribute|reference|ref|caption|label|name|alt\s+text|'
    r'feld|schlussel|schlüssel|wert|eigenschaft|attribut|referenz|beschriftung|name)\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_SOURCE_EDIT_WEB_CONTENT_RE = re.compile(
    r'\b(?:font|color|colour|style|layout|theme|selector|class|stylesheet|'
    r'schrift|farbe|stil|farbschema|selektor|klasse)\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_SOURCE_EDIT_DATA_CONTENT_RE = re.compile(
    r'\b(?:field|key|value|status|property|entry|row|column|schema|'
    r'feld|schlussel|schlüssel|wert|eigenschaft|eintrag|zeile|spalte|schema)\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_SOURCE_EDIT_CODE_CONTENT_RE = re.compile(
    r'\b(?:code|function|class|method|module|import|variable|constant|script|query|bug|'
    r'funktion|klasse|methode|modul|variable|konstante|skript|abfrage|fehler)\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_FORMAT_RE = re.compile(
    r'\b(?P<format>'
    r'html|htm|css|stylesheet|style\s*sheet|javascript|java\s*script|js|markdown|md|plain\s+text|txt|'
    r'readme|json|yaml|yml|xml|csv|svg|typescript|ts|tsx|jsx|python|py|shell|bash|sh|sql'
    r')\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_DISTINCT_FORMAT_CUE_RE = re.compile(
    r'\b(?:'
    r'dedicated|separate|stand[\s-]?alone|external|own|individual|'
    r'dediziert(?:e|en|em|er|es)?|separat(?:e|en|em|er|es)?|'
    r'getrennt(?:e|en|em|er|es)?|eigen(?:e|en|em|er|es)?|'
    r'eigenst(?:a|ä|ae)ndig(?:e|en|em|er|es)?|extern(?:e|en|em|er|es)?|'
    r'individuell(?:e|en|em|er|es)?'
    r')\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_RESPONSE_FORMAT_ONLY_EXTENSIONS = {'json'}


_JSON_TEXT_ARTIFACT_QUOTED_SPAN_RE = re.compile(
    r'"[^"\n]*"|“[^”\n]*”|`[^`\n]*`|(?<!\w)\'[^\'\n]*\'(?!\w)'
)


_JSON_TEXT_ARTIFACT_QUOTED_FILENAME_RE = re.compile(
    r'(?P<quote>["`])(?P<filename>[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.json)(?P=quote)',
    re.IGNORECASE,
)


_JSON_TEXT_ARTIFACT_QUOTED_FILENAME_ACTION_RE = re.compile(
    r'\b(?:create|save)\s+(?:(?:the|a)\s+)?file\s*$',
    re.IGNORECASE,
)


_JSON_TEXT_ARTIFACT_MANIFEST_ACTION_RE = re.compile(
    r'\b(?:'
    r'create|generate|make|write|produce|return|provide|build|emit|save|materialize|materialise|'
    r'erzeuge|erstelle|generiere|schreibe|liefere|baue|speichere|materialisiere'
    r')\b|'
    r'\b(?:must|should|shall|will|need(?:s)?\s+to|have\s+to|are\s+to)\s+(?:be\s+)?'
    r'(?:created|generated|made|written|produced|returned|provided|built|emitted|saved|'
    r'materialized|materialised)\b|'
    r'\b(?:muss|muessen|müssen|soll|sollen)\s+(?:erstellt|generiert|geschrieben|geliefert|'
    r'gebaut|gespeichert|materialisiert)\s+werden\b',
    re.IGNORECASE,
)


_JSON_TEXT_ARTIFACT_MANIFEST_TARGET_RE = re.compile(
    r'\b(?:files?|artifacts?|artefacts?|documents?|bundles?|packages?|'
    r'datei(?:en)?|artefakt(?:e|en)?|dokument(?:e|en)?|paket(?:e|en)?)\b',
    re.IGNORECASE,
)


_JSON_TEXT_ARTIFACT_MANIFEST_SOURCE_CONTEXT_RE = re.compile(
    r'\b(?:source|input|reference|referenced|selected|existing|uploaded|provided)\s+'
    r'(?:files?|artifacts?|artefacts?|documents?|bundles?|packages?|'
    r'datei(?:en)?|artefakt(?:e|en)?|dokument(?:e|en)?|paket(?:e|en)?)\b|'
    r'\b(?:using|from|based\s+on|about|inspect|review|read|mention|describe|'
    r'aus|anhand|pruefe|prüfe|lies|beschreibe)\b[^:;.!?\n]{0,96}\b'
    r'(?:files?|artifacts?|artefacts?|documents?|bundles?|packages?|'
    r'datei(?:en)?|artefakt(?:e|en)?|dokument(?:e|en)?|paket(?:e|en)?)\b',
    re.IGNORECASE,
)


_JSON_TEXT_ARTIFACT_NON_OUTPUT_LIST_CONTEXT_RE = re.compile(
    r'\b(?:comparison|summary|analysis|report|documentation|description|explanation|'
    r'overview|table|list|inventory|catalog|checksums?|hash(?:es)?|digests?|status|metadata|'
    r'references?|paths?|vergleich|zusammenfassung|analyse|bericht|'
    r'dokumentation|beschreibung|erklaerung|erklärung|uebersicht|übersicht|tabelle|liste|inventar|katalog)\b'
    r'(?:[^:;.!?\n]{0,64}\b(?:of|about|between|for|over|zu|ueber|über|zwischen|fuer|für)\b|'
    r'[^:;.!?\n]{0,24}:\s*$)|'
    r'\b(?:compare|summarize|analyse|analyze|document|describe|explain|mention|reference|'
    r'list|plan|vergleich|fasse|analysiere|dokumentiere|beschreibe|erklaere|erkläre|erwaehne|'
    r'erwähne|referenziere|liste|plane)\w*\b',
    re.IGNORECASE,
)


_JSON_TEXT_ARTIFACT_MANIFEST_DELIBERATION_RE = re.compile(
    r'\b(?:which|whether|tell\s+me|decide|assess|determine|evaluate|classify|choose|'
    r'suggested|candidate|optional|possible|potential|draft|planned|proposed|recommended|'
    r'welche|welcher|welches|ob|sage\s+mir|entscheide|bewerte|bestimme|klassifiziere|waehle|wähle|'
    r'vorgeschlagen|optional|moeglich|möglich|potenziell|entwurf|geplant|empfohlen)\b',
    re.IGNORECASE,
)


_JSON_TEXT_ARTIFACT_IMPLICIT_MANIFEST_TARGET_RE = re.compile(
    r'\b(?:the\s+following|these|those|folgende(?:n|r|s)?|diese(?:n|r|s)?)\b',
    re.IGNORECASE,
)


_JSON_TEXT_ARTIFACT_MULTILINE_QUOTED_SPAN_RE = re.compile(
    r'"[^"\n]*\n[^\"]*"|“[^”\n]*\n[^”]*”'
)


_JSON_TEXT_ARTIFACT_DIRECT_FILENAME_LIST_PREFIX_RE = re.compile(
    r'\s*(?:(?:exactly|only|the|these|those|following|named|new|local|separate|individual|'
    r'all|just|genau|nur|die|diese|folgende|genannte|neue|lokale|separate|einzelne|alle|'
    r'\d+|one|two|three|four|five|six|ein(?:e|en|em|er|es)?|zwei|drei|vier|fuenf|fünf|sechs)\s+)*',
    re.IGNORECASE,
)


_JSON_TEXT_ARTIFACT_SITE_COMPONENT_LIST_PREFIX_RE = re.compile(
    r'\b(?:site|website|web\s+(?:site|app|application)|app|application)\b'
    r'[^.;!?\n]{0,64}\b(?:with|containing|comprising|including)\s*$',
    re.IGNORECASE,
)


_JSON_TEXT_ARTIFACT_META_ACTION_PREFIX_RE = re.compile(
    r'\b(?:explain|describe|show|tell)(?:\s+(?:to\s+)?(?:me|us))?\s+'
    r'(?:how|why|whether)\s+(?:to\s+)?$',
    re.IGNORECASE,
)


_JSON_TEXT_ARTIFACT_RELATIVE_PATH_SUFFIX_RE = re.compile(
    r'(?:(?:\./)|(?:\./)?(?:[A-Za-z0-9][A-Za-z0-9._-]{0,80}/){1,6})\s*$'
)


_JSON_TEXT_ARTIFACT_MANIFEST_ITEM_RE = re.compile(
    r'^[ \t]*(?:[-*+]|\d{1,3}[.)])\s+',
    re.IGNORECASE | re.MULTILINE,
)


_JSON_TEXT_ARTIFACT_DIRECT_FILE_RE = re.compile(
    r'\bjson\b\s*(?:[-–—]\s*)?'
    r'(?:file|artifact|artefact|artefakt|datei|document|dokument)\b'
    r'(?![\s_-]+(?:path|paths|reference|references|ref|refs|field|fields|url|urls|'
    r'pfad|pfade|referenz|referenzen|feld|felder)\b)|'
    r'\bjson\b[^,;.!?\n]{0,24}\b(?:as\s+(?:a\s+)?file|als\s+datei)\b',
    re.IGNORECASE,
)


_JSON_TEXT_ARTIFACT_FILE_FORMAT_RE = re.compile(
    r'\bfile\s+in\s+json\s+format\b|'
    r'\bfile\s+formatted\s+as\s+json\b|'
    r'\bjson[-_]formatted\s+file\b',
    re.IGNORECASE,
)


_JSON_TEXT_ARTIFACT_EXTRA_ACTION_RE = re.compile(
    r'\b(?:output|export|download|persist|persistiere)\b',
    re.IGNORECASE,
)


_JSON_TEXT_ARTIFACT_FORMAT_ACTION_RE = re.compile(
    r'\b(?:save|materialize|materialise|download|export|persist|'
    r'speichere|materialisiere|persistiere)\b'
    r'(?:\s+(?:a\s+|an\s+|ein(?:e|en|em|er|es)?\s+)?json\b|'
    r'[^.;!?\n]{0,120}\b(?:as|als)\s+'
    r'(?:a\s+|an\s+|ein(?:e|en|em|er|es)?\s+)?json\b)',
    re.IGNORECASE,
)


_JSON_TEXT_ARTIFACT_NEGATION_PREFIX_RE = re.compile(
    r'\b(?:do\s+not|don[\'’]?t|dont|must\s+not|should\s+not|never|no|not|without|'
    r'kein(?:e|en|em|er|es)?|nicht|ohne)\b[^,;.!?\n]{0,96}$',
    re.IGNORECASE,
)


_JSON_TEXT_ARTIFACT_NEGATION_SUFFIX_RE = re.compile(
    r'^\s*(?:(?:must|should|is|be)\s+)?(?:not|never|nicht)\b',
    re.IGNORECASE,
)


_JSON_TEXT_ARTIFACT_NEGATED_CONTEXT_RE = re.compile(
    r'\b(?:do\s+not|don[\'’]?t|dont|must\s+not|should\s+not|never|no|not|without|'
    r'kein(?:e|en|em|er|es)?|nicht|ohne)\b[^;!?\n]{0,96}\bjson\b|'
    r'\bjson\b[^\n]{0,120}\b(?:no|not|never|without|kein(?:e|en|em|er|es)?|nicht|ohne)\b'
    r'[^\n]{0,64}\b(?:file|artifact|artefact|artefakt|datei)\b',
    re.IGNORECASE,
)


_JSON_TEXT_ARTIFACT_RESPONSE_FORMAT_RE = re.compile(
    r'\b(?:return|provide|emit|output|gib|liefere)\b[^.;!?\n]{0,120}\bjson\b|'
    r'\bjson\b\s*(?:[-–—]\s*)?(?:object|objekt|response|antwort|output|ausgabe)\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_NEGATION_RE = re.compile(
    r'\b(?:do\s+not|don[\'’]?t|without|kein|keine|keinen|nicht|ohne)\b[^.;!?\n]{0,80}\b'
    r'(?:file|artifact|artefact|artefakt|datei|download|save|speicher|persist)',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_CARDINALITY_CONSTRAINT_RE = re.compile(
    r'\b(?:do\s+not|don[\'’]?t|dont|must\s+not|should\s+not|never|no|nicht|kein(?:e|en|er|es)?)\b'
    r'(?=[^.;!?\n]{0,220}\b(?:extra|additional|duplicate|duplicated|more|further|'
    r'zusaetzlich(?:e|en|er|es)?|zusatzlich(?:e|en|er|es)?|zusätzlich(?:e|en|er|es)?|'
    r'weitere?|doppelte?)\b)'
    r'(?=[^.;!?\n]{0,240}\b(?:beyond|except|other\s+than|apart\s+from|besides|duplicate|'
    r'duplicates|instead\s+of\s+creating\s+duplicate|ueber|uber|über|ausser|außer)\b)'
    r'(?=[^.;!?\n]{0,240}\b(?:artifact(?:s)?|artefact(?:s)?|artefakt(?:e|en)?|file(?:s)?|'
    r'datei(?:en)?|asset(?:s)?|html|css|image(?:s)?|picture(?:s)?|photo(?:s)?|bild(?:er)?|'
    r'page(?:\s+file)?(?:s)?)\b)',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_GENERIC_FALLBACK_CUE_RE = re.compile(
    r'\b('
    r'file|files|datei|dateien|document|documents|dokument|dokumente|'
    r'download|downloadable|save|speicher|speichere|persist|persistiere|'
    r'write\s+to|as\s+a\s+file|als\s+datei|'
    r'(?:text|code|markdown|html|css|json)\s+(?:artifact|artefact|artefakt)'
    r')\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_COUNT_WORDS: dict[str, int] = {
    'two': 2,
    'zwei': 2,
    'three': 3,
    'drei': 3,
    'four': 4,
    'vier': 4,
    'five': 5,
    'funf': 5,
    'fuenf': 5,
    'six': 6,
    'sechs': 6,
}


_TEXT_ARTIFACT_EACH_PART_CUE_RE = re.compile(
    r'\b(?:each|every|per|je|jedes|jeden|jede|jeder|jedem)\b'
    r'[\s\S]{0,96}\b(?:part|section|chapter|teil|abschnitt|kapitel)\b'
    r'[\s\S]{0,96}\b(?:own|separate|individual|eigen(?:e|es|en|er)?|separat(?:e|es|en|er)?)\b|'
    r'\b(?:own|separate|individual|eigen(?:e|es|en|er)?|separat(?:e|es|en|er)?)\b'
    r'[\s\S]{0,96}\b(?:for\s+each|je|jedes|jeden|jede|jeder|jedem)\b'
    r'[\s\S]{0,96}\b(?:part|section|chapter|teil|abschnitt|kapitel)\b|'
    r'\b(?:part|section|chapter|teil|abschnitt|kapitel)\b'
    r'[\s\S]{0,96}\b(?:own|separate|individual|eigen(?:e|es|en|er)?|separat(?:e|es|en|er)?)\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_PART_COUNT_RE = re.compile(
    r'\b(?P<count>\d+|two|three|four|five|six|zwei|drei|vier|funf|fuenf|sechs)\b'
    r'[\s-]*(?:part|parts|section|sections|chapter|chapters|teil|teile|teilig(?:e|es|er|en)?|'
    r'abschnitt|abschnitte|kapitel)\b|'
    r'\b(?P<count_prefix>\d+|two|three|four|five|six|zwei|drei|vier|funf|fuenf|sechs)'
    r'teilig(?:e|es|er|en)?\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_FORMAT_NEGATION_RE = re.compile(
    r'\b(?:do\s+not|don[\'’]?t|dont|no|not|without|kein(?:e|en|er|es)?|nicht|ohne)\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_FORMAT_SCOPE_BOUNDARY_RE = re.compile(
    r'[;!?]|(?<!\d)\.(?=\s|$)|\b(?:but|however|aber|sondern|stattdessen)\b|'
    r'(?:,|\n|\b(?:and|und)\b)\s*(?=(?:(?:then|please|dann|bitte)\s+)?'
    r'(?:create|generate|write|produce|build|make|draw|render|save|'
    r'erzeuge|erstelle|generiere|schreibe|baue|zeichne|speichere)\b)',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_COMMAND_PROHIBITION_RE = re.compile(
    r'(?:^|[,\n]|\b(?:and|und)\b)\s*(?:(?:please|bitte)\s+)?'
    r'(?:do\s+not|don[\'’]?t|dont)\b',
    re.IGNORECASE,
)


_SVG_ARTIFACT_ACTION_RE = re.compile(
    r'\b(?:create|generate|draw|render|make|produce|build|write|'
    r'erzeuge|erstelle|generiere|zeichne|baue|schreibe)\b\s+'
    r'(?:(?:me|us|mir|uns)\s+)?',
    re.IGNORECASE,
)


_SVG_ARTIFACT_TYPED_NOUN_PATTERN = (
    r'(?:illustration|image|picture|drawing|icon|graphic|logo|'
    r'file|artifact|artefact|bild|zeichnung|grafik|datei|artefakt)'
)


_SVG_ARTIFACT_TYPED_TARGET_RE = re.compile(
    r'(?:(?:a|an|one|the|ein(?:e|en|em|er|es)?|die|das|'
    r'simple|small|new|separate|detailed|kleine?|neue?|einfache?|detaillierte?)\s+)*'
    r'(?:'
    r'(?P<prefix_format>svg|png|jpe?g)\b'
    r'(?:[\s-]+' + _SVG_ARTIFACT_TYPED_NOUN_PATTERN + r'\b)?|'
    + _SVG_ARTIFACT_TYPED_NOUN_PATTERN + r'\b\s+(?:as|als)\s+'
    r'(?P<suffix_format>svg|png|jpe?g)\b'
    r')',
    re.IGNORECASE,
)


_SVG_ARTIFACT_TARGET_JOIN_RE = re.compile(
    r'\s*(?:,\s*(?:(?:and|und)\s+)?|\b(?:and|und)\s+)',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_RESERVED_SUFFIX_RE = re.compile(
    r'^\s*(?:(?:ideas?|concepts?)\s+)?(?:as\s+)?(?:reserved|optional|for\s+later)\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_VALIDATION_ONLY_RE = re.compile(
    r'\b(?:treat|consider|count|mark|fail|fails|failing|closure|criteria|criterion|'
    r'complete|completion|incomplete|required|required\s+artifact|validation|validate|'
    r'werte|betrachte|gilt|gelte|abschluss|vollstaendig|vollständig|unvollstaendig|unvollständig|'
    r'erforderlich|pflicht|kriterium|kriterien)\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_MISSING_RE = re.compile(
    r'\b(?:missing|absent|not\s+present|not\s+created|not\s+generated|not\s+saved|'
    r'fehlt|fehlen|fehlend|nicht\s+vorhanden|nicht\s+erstellt|nicht\s+generiert|'
    r'nicht\s+gespeichert|unvollstaendig|unvollständig|incomplete)\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_DEMONSTRATIVE_REFERENCE_RE = re.compile(
    r'\b(?:this|that|it|these|those|dies|diese|dieser|dieses|das|den|dem|ihn|sie|es|daraus|davon)\b'
    r'.{0,96}\b(?:file|artifact|artefact|artefakt|datei|document|dokument|html|css|js|markdown|text)\b|'
    r'\b(?:file|artifact|artefact|artefakt|datei|document|dokument|html|css|js|markdown|text)\b'
    r'.{0,96}\b(?:this|that|it|these|those|dies|diese|dieser|dieses|das|den|dem|ihn|sie|es|daraus|davon)\b',
    re.IGNORECASE,
)


_RELATIVE_ARTIFACT_CONTENT_THAT_RE = re.compile(
    r'\b(?:audio|speech|voice|recording|image|picture|photo|illustration|'
    r'file|artifact|artefact|document|text|aufnahme|bild|datei|artefakt|dokument)\b'
    r'(?:\s+[\w-]+){0,3}\s+(?P<relative>that)\b'
    r'(?=\s+(?:says?|reads?|contains?|shows?|depicts?|features?|states?|speaks?|narrates?)\b)',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_SELF_CONTAINED_SOURCE_RE = re.compile(
    r'\b(?:create|generate|write|produce|build|make|'
    r'erzeuge|erstelle|generiere|schreibe|baue|verfasse)\b'
    r'.{0,120}\b(?:text|copy|note|notice|warning|protocol|report|caption|claim|slogan|script|'
    r'text|hinweis|warnhinweis|notiz|protokoll|bericht|caption|claim|slogan|skript|zeile)\b'
    r'.{0,180}\b(?:save|persist|speichere|persistiere|artifact|artefact|artefakt|file|datei)\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_SAME_PROMPT_GENERATED_SOURCE_RE = re.compile(
    r'\b(?:create|generate|write|produce|build|make|'
    r'erzeuge|erstelle|generiere|schreibe|baue|verfasse)\b'
    r'(?:\s+(?:me|mir|uns))?[\s,]*(?:an?\b|one\b|the\b|'
    r'einen?\b|eine\b|ein\b|den\b|die\b|das\b|'
    r'kurzen?\b|kurzes?\b|short\b|brief\b|concise\b)'
    r'[\s\S]{0,220}\b(?:it|ihn|sie|es|das|den|diese|diesen|daraus|davon)\b'
    r'[\s\S]{0,140}\b(?:save|saved|speichere|persist|persistiere|'
    r'artifact|artefact|artefakt|file|datei)\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_SELF_CONTAINED_CODE_BUNDLE_RE = re.compile(
    r'\b(?:create|generate|write|produce|build|make|'
    r'erzeuge|erstelle|generiere|schreibe|baue|verfasse)\b'
    r'[\s\S]{0,240}\bhtml\b[\s\S]{0,96}\bcss\b'
    r'[\s\S]{0,160}\b(?:artifact(?:s)?|artefact(?:s)?|artefakt(?:e|en)?|file(?:s)?|datei(?:en)?)\b|'
    r'\b(?:create|generate|write|produce|build|make|'
    r'erzeuge|erstelle|generiere|schreibe|baue|verfasse)\b'
    r'[\s\S]{0,180}\b(?:artifact(?:s)?|artefact(?:s)?|artefakt(?:e|en)?|file(?:s)?|datei(?:en)?)\b'
    r'[\s\S]{0,160}\bhtml\b[\s\S]{0,96}\bcss\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_IMPLICIT_WEB_PAGE_RE = re.compile(
    r'\b(?:'
    r'landing\s*page|landingpage|product\s*page|sales\s*page|web\s?page|website|webseite|homepage|startseite|'
    r'(?:produkt|verkaufs|angebots|promo|marketing|shop|portfolio|profil|event|projekt|kampagnen|marken|'
    r'reise|tourismus|touren|ferien|urlaubs|hotel|destinations?)seite'
    r')\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_BARE_GERMAN_PAGE_RE = re.compile(r'\bseite\b', re.IGNORECASE)


_TEXT_ARTIFACT_WEB_PAGE_NEED_CUE_RE = re.compile(
    r'\b(?:need|want|require|brauch(?:e|en|st|t)?|ben[oö]tig(?:e|en|st|t)?|'
    r'h[aä]tte(?:st|n)?\s+gern(?:e)?|w[uü]nsch(?:e|en|st|t)?)\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_GENERATED_VISUAL_CONTEXT_RE = re.compile(
    r'\b(?:generate|create|render|make|show|generier(?:e|en)?|erzeug(?:e|en)?|erstelle|erstellen|mach(?:e|en)?|zeige)\w*\b'
    r'[^.;!?\n]{0,180}\b(?:image|images|picture|pictures|photo|photos|bild|bilder|foto|fotos)\b|'
    r'\b(?:image|images|picture|pictures|photo|photos|bild|bilder|foto|fotos)\b'
    r'[^.;!?\n]{0,180}\b(?:generate|create|render|make|show|generier(?:e|en)?|erzeug(?:e|en)?|erstelle|erstellen|mach(?:e|en)?|zeige)\w*\b|'
    r'\b(?:exactly|genau)?\s*(?:\d+|one|two|three|four|five|six|ein(?:e|s|en)?|zwei|drei|vier|fuenf|fünf|sechs)\s+'
    r'(?:image|images|picture|pictures|photo|photos|bild|bilder|foto|fotos)\b',
    re.IGNORECASE,
)


_TEXT_ARTIFACT_INLINE_SOURCE_RE = re.compile(
    r'(?is)('
    r'(?:content|code|source|html|css|javascript|json|markdown|text|following|below|inhalt|quelle|code)\s*:\s*\S.{20,}|'
    r':\s*(?:<!doctype\s+html\b|<html\b|<[a-z][\w:-]*(?:\s|>|/)|\{|\[|function\b|const\b|let\b|var\b|body\s*\{)'
    r')'
)


_TEXT_ARTIFACT_SELF_CLAIM_RE = re.compile(
    r'(?is)('
    r'\[artifact:\s*[^\]]+\]|'
    r'artifact created|'
    r'artifact generated|'
    r'saved locally|'
    r'saved as a local artifact|'
    r'downloadable artifact|'
    r'ready-to-run artifact|'
    r'ready to be downloaded'
    r')'
)


_TEXT_ARTIFACT_FENCED_BLOCK_RE = re.compile(
    r'```(?P<lang>[A-Za-z0-9_+.-]*)(?:[^\n`]*)?\n(?P<body>.*?)(?:\n```|```)',
    re.DOTALL,
)


_TEXT_ARTIFACT_TAG_RE = re.compile(
    r'(?is)<artifact\b(?P<attrs>[^>]*)>(?P<body>.*?)</artifact>'
)


_TEXT_ARTIFACT_TAG_ATTR_RE = re.compile(
    r'(?P<name>[A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?P<quote>["\'])(?P<value>.*?)(?P=quote)',
    re.DOTALL,
)


_TEXT_ARTIFACT_BLOCKED_CONTENT_RE = re.compile(
    r'(?is)\b('
    r'i\s+(?:cannot|can[\'’]?t)\s+(?:proceed|create|generate|make|write)|'
    r'cannot\s+(?:proceed|create|generate|make|write)|'
    r'awaiting\s+(?:clarification|input)|'
    r'needs?\s+(?:clarification|content|input|specification)|'
    r'missing\s+(?:content|input|specification)|'
    r'not\s+included\s+in\s+your\s+request|'
    r'please\s+provide\s+(?:the\s+)?(?:html|code|content|description|specification)|'
    r'provide\s+(?:the\s+)?(?:html|code|content|description|specification)'
    r')\b',
)


_TEXT_ARTIFACT_NON_PAYLOAD_LANGS = {
    'analysis',
    'reasoning',
    'thought',
    'thinking',
    'plan',
}


_TEXT_ARTIFACT_LANGUAGE_EXTENSIONS = {
    'md': 'md',
    'markdown': 'md',
    'html': 'html',
    'htm': 'html',
    'css': 'css',
    'js': 'js',
    'javascript': 'js',
    'mjs': 'js',
    'cjs': 'js',
    'ts': 'ts',
    'typescript': 'ts',
    'tsx': 'tsx',
    'jsx': 'jsx',
    'json': 'json',
    'yaml': 'yaml',
    'yml': 'yaml',
    'xml': 'xml',
    'csv': 'csv',
    'svg': 'svg',
    'py': 'py',
    'python': 'py',
    'sh': 'sh',
    'bash': 'sh',
    'shell': 'sh',
    'sql': 'sql',
    'txt': 'txt',
    'text': 'txt',
}


_TEXT_ARTIFACT_CONTROL_JSON_KEYS = {
    'candidate_graph',
    'decision_contract',
    'output_candidates',
    'output_obligations',
    'promotion_review',
    'request_ir',
    'request_phase_graph',
    'user_facing_response',
    'workload_graph',
}


def _normalize_text_artifact_extension(value: str) -> Optional[str]:
    token = re.sub(r'[^a-z0-9]+', '', str(value or '').strip().lower().lstrip('.'))
    aliases = {
        'plaintext': 'txt',
        'text': 'txt',
        'markdown': 'md',
        'readme': 'md',
        'stylesheet': 'css',
        'javascript': 'js',
        'java script': 'js',
        'typescript': 'ts',
        'python': 'py',
        'shell': 'sh',
        'bash': 'sh',
    }
    token = aliases.get(token, token)
    if token == 'markdown':
        token = 'md'
    if token in TEXT_ARTIFACT_EXTENSIONS:
        return 'md' if token == 'markdown' else token
    return None


def _text_artifact_source_name_is_local_target(scope: str, source_name: Optional[str]) -> bool:
    name = str(source_name or '').strip()
    if not name:
        return False
    tokens = [token for token in re.split(r'[\s._-]+', name) if token]
    if not tokens:
        return False
    pattern = r'[\s._-]+'.join(re.escape(token) for token in tokens)
    return bool(re.search(rf'(?<!\w){pattern}(?!\w)', scope, flags=re.IGNORECASE))


def _text_artifact_source_format_is_local_target(scope: str, source_extension: str) -> bool:
    normalized_source = _normalize_text_artifact_extension(source_extension or '')
    if not normalized_source:
        return False
    return any(
        _normalize_text_artifact_extension(match.group('format') or '') == normalized_source
        for match in _TEXT_ARTIFACT_FORMAT_RE.finditer(scope)
    )


def _text_artifact_source_content_is_local_target(scope: str, source_extension: str) -> bool:
    normalized_source = _normalize_text_artifact_extension(source_extension or '') or ''
    if _TEXT_ARTIFACT_SOURCE_EDIT_COMMON_CONTENT_RE.search(scope):
        return True
    if normalized_source in {'html', 'htm', 'css', 'svg'}:
        return bool(_TEXT_ARTIFACT_SOURCE_EDIT_WEB_CONTENT_RE.search(scope))
    if normalized_source in {'json', 'yaml', 'yml', 'xml', 'csv'}:
        return bool(_TEXT_ARTIFACT_SOURCE_EDIT_DATA_CONTENT_RE.search(scope))
    if normalized_source in {'js', 'mjs', 'cjs', 'ts', 'tsx', 'jsx', 'py', 'sh', 'sql'}:
        return bool(_TEXT_ARTIFACT_SOURCE_EDIT_CODE_CONTENT_RE.search(scope))
    return False


def _text_artifact_source_strong_content_is_local_target(scope: str, source_extension: str) -> bool:
    normalized_source = _normalize_text_artifact_extension(source_extension or '') or ''
    if _TEXT_ARTIFACT_SOURCE_EDIT_STRONG_CONTENT_RE.search(scope):
        return True
    if normalized_source in {'html', 'htm', 'css', 'svg'}:
        return bool(_TEXT_ARTIFACT_SOURCE_EDIT_WEB_CONTENT_RE.search(scope))
    if normalized_source in {'json', 'yaml', 'yml', 'xml', 'csv'}:
        return bool(_TEXT_ARTIFACT_SOURCE_EDIT_DATA_CONTENT_RE.search(scope))
    if normalized_source in {'js', 'mjs', 'cjs', 'ts', 'tsx', 'jsx', 'py', 'sh', 'sql'}:
        return bool(_TEXT_ARTIFACT_SOURCE_EDIT_CODE_CONTENT_RE.search(scope))
    return False


def _text_artifact_selected_source_edit_is_bound(
    text: str,
    *,
    source_extension: str,
    source_name: Optional[str],
    response_json_only: bool,
) -> bool:
    """Return true when an edit action locally targets the selected text source."""

    prompt = str(text or '').strip()
    if not prompt or not _TEXT_ARTIFACT_SOURCE_EDIT_CUE_RE.search(prompt):
        return False
    for clause_match in _TEXT_ARTIFACT_SOURCE_EDIT_CLAUSE_RE.finditer(prompt):
        clause = clause_match.group(0)
        actions = list(_TEXT_ARTIFACT_SOURCE_EDIT_ACTION_RE.finditer(clause))
        for action in actions:
            action_tail = clause[action.end():]
            next_directive = _TEXT_ARTIFACT_SOURCE_EDIT_NEXT_DIRECTIVE_RE.search(action_tail)
            if next_directive:
                action_tail = action_tail[:next_directive.start()]
            local_scope = action_tail[:160]
            if not local_scope.strip():
                continue
            normalized_source = _normalize_text_artifact_extension(source_extension or '') or ''
            json_response_target = None
            if response_json_only:
                json_response_target = (
                    _TEXT_ARTIFACT_SOURCE_EDIT_JSON_TARGET_RE.search(local_scope)
                    if normalized_source != 'json'
                    else _TEXT_ARTIFACT_SOURCE_EDIT_QUALIFIED_JSON_RESPONSE_TARGET_RE.search(local_scope)
                )
            if json_response_target:
                binding_scope = local_scope[:json_response_target.start()]
                if _TEXT_ARTIFACT_SOURCE_EDIT_EXPLICIT_SOURCE_RE.search(binding_scope):
                    return True
                if _text_artifact_source_name_is_local_target(binding_scope, source_name):
                    return True
                continue
            competing_target = _TEXT_ARTIFACT_SOURCE_EDIT_COMPETING_TARGET_RE.search(local_scope)
            prior_binding_scope = (
                local_scope[:competing_target.start()]
                if competing_target
                else local_scope
            )
            prior_scope = clause[:action.start()]
            prior_competing_target = _TEXT_ARTIFACT_SOURCE_EDIT_COMPETING_TARGET_RE.search(prior_scope)
            prior_json_response_target = bool(
                response_json_only
                and _JSON_TEXT_ARTIFACT_RESPONSE_FORMAT_RE.search(prior_scope)
            )
            if prior_json_response_target:
                if _TEXT_ARTIFACT_SOURCE_EDIT_EXPLICIT_SOURCE_RE.search(prior_binding_scope):
                    return True
                if _text_artifact_source_name_is_local_target(prior_binding_scope, source_name):
                    return True
                if _text_artifact_source_format_is_local_target(prior_binding_scope, source_extension):
                    return True
                continue
            compound_content_target = bool(
                _TEXT_ARTIFACT_SOURCE_EDIT_COMPOUND_CONTENT_RE.search(local_scope)
            )
            if prior_competing_target:
                if _TEXT_ARTIFACT_SOURCE_EDIT_EXPLICIT_SOURCE_RE.search(prior_binding_scope):
                    return True
                if _text_artifact_source_name_is_local_target(prior_binding_scope, source_name):
                    return True
                if _text_artifact_source_format_is_local_target(prior_binding_scope, source_extension):
                    return True
                if compound_content_target or _text_artifact_source_strong_content_is_local_target(
                    local_scope,
                    source_extension,
                ):
                    return True
                continue
            if not competing_target:
                # With one selected source and no other explicit target, the
                # action's implicit object remains that source (for example,
                # "Add a footer" or "Replace the introduction").
                return True
            if compound_content_target:
                return True
            binding_scope = (
                local_scope[:competing_target.start()]
            )
            if _TEXT_ARTIFACT_SOURCE_EDIT_EXPLICIT_SOURCE_RE.search(binding_scope):
                return True
            if _TEXT_ARTIFACT_SOURCE_EDIT_DIRECT_PRONOUN_RE.search(binding_scope):
                return True
            if _text_artifact_source_format_is_local_target(binding_scope, source_extension):
                return True
            if _text_artifact_source_name_is_local_target(binding_scope, source_name):
                return True
            if _text_artifact_source_content_is_local_target(binding_scope, source_extension):
                return True
    return False


def _text_artifact_count_from_token(value: str) -> int:
    token = re.sub(r'[^a-z0-9]+', '', str(value or '').strip().lower())
    if not token:
        return 0
    if token.isdigit():
        parsed = int(token)
        return parsed if parsed > 0 else 0
    return int(_TEXT_ARTIFACT_COUNT_WORDS.get(token, 0))


def _text_artifact_each_part_count(text: str) -> int:
    prompt = str(text or '').strip()
    if not prompt or not _TEXT_ARTIFACT_EACH_PART_CUE_RE.search(prompt):
        return 0
    counts = [
        _text_artifact_count_from_token(match.group('count') or match.group('count_prefix') or '')
        for match in _TEXT_ARTIFACT_PART_COUNT_RE.finditer(prompt)
    ]
    counts = [count for count in counts if count > 1]
    return max(counts) if counts else 0


def _normalize_text_artifact_block_language(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', str(value or '').strip().lower())


def _text_artifact_block_language_is_payload(language: str) -> bool:
    lang = _normalize_text_artifact_block_language(language)
    return lang not in _TEXT_ARTIFACT_NON_PAYLOAD_LANGS


def _text_artifact_block_extension(language: str) -> Optional[str]:
    lang = _normalize_text_artifact_block_language(language)
    if not lang or lang in _TEXT_ARTIFACT_NON_PAYLOAD_LANGS:
        return None
    return _TEXT_ARTIFACT_LANGUAGE_EXTENSIONS.get(lang)


def normalize_text_artifact_extension(value: str) -> Optional[str]:
    return _normalize_text_artifact_extension(value)


def prompt_has_inline_text_artifact_source(prompt: str) -> bool:
    text = str(prompt or '').strip()
    return bool(
        _TEXT_ARTIFACT_FENCED_BLOCK_RE.search(text)
        or _TEXT_ARTIFACT_INLINE_SOURCE_RE.search(text)
    )


def _text_artifact_format_match_is_negated(text: str, match: re.Match[str]) -> bool:
    prefix = str(text or '')[:match.start()]
    # Wrapped exclusion lists remain one command. Only an actual sentence,
    # contrast or new action starts a fresh polarity scope, not a character cap.
    scope_start = 0
    # Include the matched token for lookahead when the token itself is a new
    # action (", create ..."); it still stays outside the governing prefix.
    for boundary in _TEXT_ARTIFACT_FORMAT_SCOPE_BOUNDARY_RE.finditer(text[:match.end()]):
        if boundary.end() > match.start():
            break
        if (
            boundary.group().strip().lower() in {'and', 'und'}
            and _TEXT_ARTIFACT_COMMAND_PROHIBITION_RE.search(
                prefix[scope_start:boundary.start()],
            )
        ):
            # "Do not generate X and create Y" prohibits both coordinated
            # commands. "Create X with no external assets, and create Y" has
            # an object constraint, so its independent action resets scope.
            continue
        scope_start = boundary.end()
    prefix = prefix[scope_start:]
    prefix = re.sub(
        r"\b(?:(?:do\s+not|don[\'’]?t|dont|not)\s+just|not\s+only|nicht\s+nur)\b",
        '',
        prefix,
        flags=re.IGNORECASE,
    )
    return bool(_TEXT_ARTIFACT_FORMAT_NEGATION_RE.search(prefix))


def explicit_svg_artifact_request_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Return affirmative SVG target spans governed by a local creation action.

    These bounded input spans distinguish requested SVG text artifacts from
    binary image generation. The action stays outside the spans because it can
    govern a coordinated PNG/JPEG target too. A target's subject description is
    included; an independent action or typed sibling target ends its scope.
    These are input intent spans, never production or fulfillment evidence.
    """
    prompt = str(text or '')
    spans: list[tuple[int, int]] = []
    for action in _SVG_ARTIFACT_ACTION_RE.finditer(prompt):
        prefix = prompt[:action.start()]
        if _JSON_TEXT_ARTIFACT_META_ACTION_PREFIX_RE.search(prefix):
            continue
        target = _SVG_ARTIFACT_TYPED_TARGET_RE.match(prompt, action.end())
        while target:
            boundary = _TEXT_ARTIFACT_FORMAT_SCOPE_BOUNDARY_RE.search(prompt, target.end())
            scope_end = boundary.start() if boundary else len(prompt)
            next_target = None
            for join in _SVG_ARTIFACT_TARGET_JOIN_RE.finditer(prompt, target.end(), scope_end):
                next_target = _SVG_ARTIFACT_TYPED_TARGET_RE.match(prompt, join.end(), scope_end)
                if next_target:
                    break
            requested_format = target.group('prefix_format') or target.group('suffix_format')
            if requested_format.lower() == 'svg':
                svg_format_match = next(
                    match for match in _TEXT_ARTIFACT_FORMAT_RE.finditer(
                        prompt, target.start(), target.end(),
                    )
                    if match.group('format').lower() == 'svg'
                )
                if (
                    not _text_artifact_format_match_is_negated(prompt, svg_format_match)
                    and not _json_text_artifact_span_is_inside_quoted_instruction(
                        prompt, action.start(), target.end(),
                    )
                ):
                    # Remove the outgoing list connector with its SVG target,
                    # leaving the shared action adjacent to a surviving raster
                    # target even when that target has no explicit image noun.
                    end = next_target.start() if next_target else scope_end
                    spans.append((target.start(), end))
            target = next_target
    return tuple(spans)


def _text_artifact_format_is_embedded(text: str, match: re.Match[str]) -> bool:
    """An inline implementation format is not a request for a sibling file."""
    return bool(re.search(
        r'\b(?:inline|embedded|eingebettet\w*)[\s-]+$',
        text[:match.start()],
        flags=re.IGNORECASE,
    ))


def _text_artifact_match_scope(text: str, start: int, end: int) -> tuple[str, int, int]:
    prompt = str(text or '')
    start_index = max(0, int(start or 0))
    end_index = min(len(prompt), max(start_index, int(end or start_index)))
    lower = max(
        prompt.rfind('.', 0, start_index),
        prompt.rfind('!', 0, start_index),
        prompt.rfind('?', 0, start_index),
        prompt.rfind(';', 0, start_index),
        prompt.rfind('\n', 0, start_index),
    )
    end_candidates = [
        index
        for index in (
            prompt.find('.', end_index),
            prompt.find('!', end_index),
            prompt.find('?', end_index),
            prompt.find(';', end_index),
            prompt.find('\n', end_index),
        )
        if index >= 0
    ]
    upper = min(end_candidates) if end_candidates else len(prompt)
    return prompt[lower + 1:upper].strip(), lower + 1, upper


@dataclass(frozen=True)
class _JsonTextArtifactIntent:
    """Bounded JSON-only materialization decision for one prompt."""

    format_spans: frozenset[tuple[int, int]] = frozenset()
    extension_spans: frozenset[tuple[int, int]] = frozenset()
    suppress_generic_fallback: bool = False

    @property
    def has_materialization(self) -> bool:
        return bool(self.format_spans or self.extension_spans)


def _mask_json_text_artifact_quotes(text: str) -> tuple[str, bool]:
    prompt = str(text or '')
    masked = list(prompt)
    quoted_json = False
    for match in _JSON_TEXT_ARTIFACT_QUOTED_SPAN_RE.finditer(prompt):
        quoted_json = quoted_json or bool(re.search(r'\bjson\b', match.group(0), re.IGNORECASE))
        for index in range(match.start(), match.end()):
            masked[index] = ' '
    return ''.join(masked), quoted_json


def _json_text_artifact_candidate_state(text: str, start: int, end: int) -> tuple[bool, bool]:
    scope, scope_start, _ = _text_artifact_match_scope(text, start, end)
    if not scope:
        return False, False
    relative_start = max(0, start - scope_start)
    relative_end = min(len(scope), max(relative_start, end - scope_start))
    negated = bool(
        _JSON_TEXT_ARTIFACT_NEGATION_PREFIX_RE.search(scope[:relative_start])
        or _JSON_TEXT_ARTIFACT_NEGATION_SUFFIX_RE.search(scope[relative_end:])
    )
    has_action = bool(
        _TEXT_ARTIFACT_ACTION_CUE_RE.search(scope)
        or _JSON_TEXT_ARTIFACT_EXTRA_ACTION_RE.search(scope)
    )
    return negated, has_action


def _json_text_artifact_span_is_inside_quoted_instruction(
    text: str,
    start: int,
    end: int,
) -> bool:
    source = str(text or '')
    quoted_spans = [
        *_JSON_TEXT_ARTIFACT_QUOTED_SPAN_RE.finditer(source),
        *_JSON_TEXT_ARTIFACT_MULTILINE_QUOTED_SPAN_RE.finditer(source),
        *_TEXT_ARTIFACT_FENCED_BLOCK_RE.finditer(source),
    ]
    return any(quoted.start() < start and end < quoted.end() for quoted in quoted_spans)


def _json_text_artifact_manifest_header_has_output_authority(
    header: str,
    *,
    allow_implicit_target: bool = False,
    allow_terminal_period: bool = False,
) -> bool:
    candidate = str(header or '').strip()
    if not candidate or not (
        candidate.endswith(':')
        or (allow_terminal_period and candidate.endswith('.'))
    ):
        return False
    for action in reversed(list(_JSON_TEXT_ARTIFACT_MANIFEST_ACTION_RE.finditer(candidate))):
        if _json_text_artifact_span_is_inside_quoted_instruction(
            candidate,
            action.start(),
            action.end(),
        ):
            continue
        negated, _ = _json_text_artifact_candidate_state(
            candidate,
            action.start(),
            action.end(),
        )
        if negated:
            continue
        scope, _, _ = _text_artifact_match_scope(candidate, action.start(), action.end())
        if (
            (
                _JSON_TEXT_ARTIFACT_MANIFEST_TARGET_RE.search(scope)
                or (
                    allow_implicit_target
                    and _JSON_TEXT_ARTIFACT_IMPLICIT_MANIFEST_TARGET_RE.search(scope)
                )
            )
            and not _JSON_TEXT_ARTIFACT_MANIFEST_SOURCE_CONTEXT_RE.search(scope)
            and not _JSON_TEXT_ARTIFACT_NON_OUTPUT_LIST_CONTEXT_RE.search(scope)
            and not _JSON_TEXT_ARTIFACT_MANIFEST_DELIBERATION_RE.search(scope)
        ):
            return True
    return False


def _json_text_artifact_list_separator_only(value: str) -> bool:
    candidate = re.sub(r'["\'`“”‘’]', '', str(value or ''))
    candidate = _JSON_TEXT_ARTIFACT_RELATIVE_PATH_SUFFIX_RE.sub('', candidate)
    candidate = re.sub(
        r'\b(?:and|or|plus|und|oder|sowie|as\s+well\s+as)\b',
        '',
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(r'\d{1,3}[.)]', '', candidate)
    candidate = re.sub(r'[\s,;/&+]+', '', candidate)
    return not candidate


def _json_text_artifact_manifest_item_line(value: str) -> bool:
    candidate = str(value or '').strip()
    marker = _JSON_TEXT_ARTIFACT_MANIFEST_ITEM_RE.match(candidate)
    if marker:
        candidate = candidate[marker.end():].strip()
    filename = _TEXT_ARTIFACT_EXTENSION_RE.search(candidate)
    filename_prefix = candidate[:filename.start()].strip(' \t"\'`“”‘’') if filename else ''
    if (
        not filename
        or (
            filename_prefix
            and not _JSON_TEXT_ARTIFACT_RELATIVE_PATH_SUFFIX_RE.fullmatch(filename_prefix)
        )
    ):
        return False
    suffix = candidate[filename.end():].strip(' \t"\'`“”‘’')
    return bool(
        not suffix
        or re.fullmatch(r'\([^()\n]{1,160}\)', suffix)
        or re.fullmatch(r'[-–—:]\s+[^\n]{1,160}', suffix)
    )


def _json_text_artifact_manifest_sibling_line(value: str) -> bool:
    candidate = str(value or '')
    return bool(
        _json_text_artifact_manifest_item_line(candidate)
        or _JSON_TEXT_ARTIFACT_MANIFEST_ITEM_RE.match(candidate)
        or re.match(r'^[ \t]{2,}\S', candidate)
    )


def _text_artifact_filename_has_declaration_authority(
    text: str, start: int, end: int,
) -> bool:
    """Carry a file-creation header across adjacent named file specifications.

    A specification is a filename followed by its required content/format, not
    a source mention or response-format instruction. Use the existing manifest
    authority and negation rules; quoted payload punctuation is not a boundary.
    """
    masked, _ = _mask_json_text_artifact_quotes(str(text or ''))
    filenames = list(_TEXT_ARTIFACT_EXTENSION_RE.finditer(masked))
    filename_dots = {index for match in filenames
                     for index in range(match.start(), match.end()) if masked[index] == '.'}
    boundaries = [match.start() for match in re.finditer(r'[.;!?\n]', masked[:start])
                  if match.start() not in filename_dots]
    clause_start = boundaries[-1] + 1 if boundaries else 0

    def specification(clause: str) -> bool:
        filename = _TEXT_ARTIFACT_EXTENSION_RE.search(clause)
        if not filename or clause[:filename.start()].strip(' \t`\"\''):
            return False
        if not re.match(r'\s*(?:must|shall|should|muss|soll)\s+'
                        r'(?:contain|include|be|enthalten|beinhalten|sein)\b',
                        clause[filename.end():], flags=re.IGNORECASE):
            return False
        negated, _ = _json_text_artifact_candidate_state(clause, filename.start(), filename.end())
        return not negated

    if not specification(masked[clause_start:]):
        return False
    # Only a contiguous run of specifications can inherit the preceding header.
    # An intervening source, discussion, or independent command ends that scope.
    previous_end = clause_start - 1
    for boundary in reversed([-1, *boundaries[:-1]]):
        clause = masked[boundary + 1:previous_end].strip()
        previous_end = boundary
        if not clause:
            continue
        if _json_text_artifact_manifest_header_has_output_authority(
            clause + '.', allow_terminal_period=True,
        ):
            return True
        if not specification(clause):
            return False
    return False


def _json_text_artifact_filename_has_manifest_authority(
    text: str,
    start: int,
    end: int,
) -> bool:
    """Bind one named JSON file to a bounded explicit file manifest."""

    prompt = str(text or '')
    target_start = max(0, int(start or 0))
    target_end = min(len(prompt), max(target_start, int(end or target_start)))
    if _json_text_artifact_span_is_inside_quoted_instruction(
        prompt,
        target_start,
        target_end,
    ):
        return False
    if _text_artifact_filename_has_declaration_authority(prompt, target_start, target_end):
        return True
    line_start = prompt.rfind('\n', 0, target_start) + 1
    line_end = prompt.find('\n', target_end)
    if line_end < 0:
        line_end = len(prompt)
    line = prompt[line_start:line_end]
    local_target_start = target_start - line_start
    local_target_end = target_end - line_start

    if _json_text_artifact_manifest_item_line(line):
        block_prefix = prompt[:line_start]
        blank_boundaries = list(re.finditer(r'\n[ \t]*\n', block_prefix))
        block_start = blank_boundaries[-1].end() if blank_boundaries else 0
        preceding_block = prompt[block_start:line_start]
        preceding_lines = preceding_block.splitlines()
        first_item_index = next(
            (
                index
                for index, preceding_line in enumerate(preceding_lines)
                if _json_text_artifact_manifest_sibling_line(preceding_line)
            ),
            len(preceding_lines),
        )
        header = '\n'.join(preceding_lines[:first_item_index])
        item_lines = preceding_lines[first_item_index:]
        if not header.strip() and item_lines and block_start > 0:
            earlier = prompt[:block_start].rstrip()
            earlier_boundaries = list(re.finditer(r'\n[ \t]*\n', earlier))
            earlier_start = earlier_boundaries[-1].end() if earlier_boundaries else 0
            header = earlier[earlier_start:]
        if all(
            not item_line.strip() or _json_text_artifact_manifest_sibling_line(item_line)
            for item_line in item_lines
        ) and _json_text_artifact_manifest_header_has_output_authority(
            header,
            allow_implicit_target=True,
            allow_terminal_period=True,
        ):
            return True

    filename_matches = list(_TEXT_ARTIFACT_EXTENSION_RE.finditer(line))
    target_index = next(
        (
            index
            for index, filename in enumerate(filename_matches)
            if filename.start() < local_target_end and local_target_start < filename.end()
        ),
        -1,
    )
    if target_index < 0:
        return False
    target_match = filename_matches[target_index]
    action_matches = [
        action
        for action in _JSON_TEXT_ARTIFACT_MANIFEST_ACTION_RE.finditer(line)
        if action.end() <= target_match.start()
        and not _json_text_artifact_span_is_inside_quoted_instruction(
            line,
            action.start(),
            action.end(),
        )
    ]
    for action in reversed(action_matches):
        negated, _ = _json_text_artifact_candidate_state(line, action.start(), action.end())
        if negated or _JSON_TEXT_ARTIFACT_META_ACTION_PREFIX_RE.search(
            line[:action.start()]
        ):
            continue
        chain = [
            filename
            for filename in filename_matches
            if filename.start() >= action.end()
        ]
        if not chain or target_match not in chain:
            continue
        prefix = line[action.end():chain[0].start()]
        classified_prefix = _JSON_TEXT_ARTIFACT_RELATIVE_PATH_SUFFIX_RE.sub('', prefix)
        if (
            len(classified_prefix) > 200
            or re.search(r'[.!?]', classified_prefix)
            or _JSON_TEXT_ARTIFACT_MANIFEST_SOURCE_CONTEXT_RE.search(classified_prefix)
            or _JSON_TEXT_ARTIFACT_NON_OUTPUT_LIST_CONTEXT_RE.search(classified_prefix)
        ):
            continue
        action_token = str(action.group(0) or '').strip().lower()
        if (
            action_token in {'return', 'provide'}
            and re.search(
                r'\b(?:review|inspect|read|analyse|analyze|pruefe|prüfe|lies|analysiere)\b'
                r'[^.;!?\n]{0,64}\b(?:and|then|und|dann)\s*$',
                line[:action.start()],
                flags=re.IGNORECASE,
            )
        ):
            continue
        coordinated_chain = [chain[0]]
        for previous, candidate in zip(chain, chain[1:]):
            if not _json_text_artifact_list_separator_only(
                line[previous.end():candidate.start()]
            ):
                break
            coordinated_chain.append(candidate)
        if target_match not in coordinated_chain:
            continue
        has_manifest_target = bool(
            _JSON_TEXT_ARTIFACT_MANIFEST_TARGET_RE.search(classified_prefix)
            or _JSON_TEXT_ARTIFACT_SITE_COMPONENT_LIST_PREFIX_RE.search(classified_prefix)
        )
        has_direct_filename_prefix = bool(
            _JSON_TEXT_ARTIFACT_DIRECT_FILENAME_LIST_PREFIX_RE.fullmatch(classified_prefix)
        )
        if len(coordinated_chain) > 1 and (
            has_manifest_target or has_direct_filename_prefix
        ):
            return True
        inline_header = line[:chain[0].start()]
        if _json_text_artifact_manifest_header_has_output_authority(inline_header):
            return True
    return False


def _json_text_artifact_intent(text: str) -> _JsonTextArtifactIntent:
    """Separate JSON response formatting from explicit JSON file materialization."""

    prompt = str(text or '')
    masked, quoted_json = _mask_json_text_artifact_quotes(prompt)
    format_matches = [
        match
        for match in _TEXT_ARTIFACT_FORMAT_RE.finditer(masked)
        if _normalize_text_artifact_extension(match.group('format') or '') == 'json'
    ]
    extension_matches = [
        match
        for match in _TEXT_ARTIFACT_EXTENSION_RE.finditer(masked)
        if _normalize_text_artifact_extension(match.group('ext') or '') == 'json'
    ]
    format_spans: set[tuple[int, int]] = set()
    extension_spans: set[tuple[int, int]] = set()
    negated_materialization = False

    def add_format_spans(candidate_start: int, candidate_end: int) -> None:
        for format_match in format_matches:
            if candidate_start <= format_match.start() and format_match.end() <= candidate_end:
                format_spans.add((format_match.start(), format_match.end()))

    for pattern, action_is_in_candidate in (
        (_JSON_TEXT_ARTIFACT_DIRECT_FILE_RE, False),
        (_JSON_TEXT_ARTIFACT_FILE_FORMAT_RE, False),
        (_JSON_TEXT_ARTIFACT_FORMAT_ACTION_RE, True),
    ):
        for candidate in pattern.finditer(masked):
            negated, has_action = _json_text_artifact_candidate_state(
                masked,
                candidate.start(),
                candidate.end(),
            )
            if negated:
                negated_materialization = True
            elif action_is_in_candidate or has_action:
                add_format_spans(candidate.start(), candidate.end())

    for extension_match in extension_matches:
        negated, has_action = _json_text_artifact_candidate_state(
            masked,
            extension_match.start(),
            extension_match.end(),
        )
        if negated:
            negated_materialization = True
        elif has_action or _json_text_artifact_filename_has_manifest_authority(
            prompt,
            extension_match.start(),
            extension_match.end(),
        ):
            extension_spans.add((extension_match.start(), extension_match.end()))

    quoted_spans = list(_JSON_TEXT_ARTIFACT_QUOTED_SPAN_RE.finditer(prompt))
    for quoted_filename in _JSON_TEXT_ARTIFACT_QUOTED_FILENAME_RE.finditer(prompt):
        if any(
            quote_span.start() < quoted_filename.start()
            and quoted_filename.end() < quote_span.end()
            for quote_span in quoted_spans
        ):
            continue
        _, scope_start, _ = _text_artifact_match_scope(
            prompt,
            quoted_filename.start(),
            quoted_filename.end(),
        )
        if (
            not _JSON_TEXT_ARTIFACT_QUOTED_FILENAME_ACTION_RE.search(
                prompt[scope_start:quoted_filename.start()]
            )
            and not _json_text_artifact_filename_has_manifest_authority(
                prompt,
                quoted_filename.start(),
                quoted_filename.end(),
            )
        ):
            continue
        negated, _ = _json_text_artifact_candidate_state(
            prompt,
            quoted_filename.start(),
            quoted_filename.end(),
        )
        if negated:
            negated_materialization = True
            continue
        filename_match = _TEXT_ARTIFACT_EXTENSION_RE.fullmatch(
            quoted_filename.group('filename') or ''
        )
        if not filename_match:
            continue
        filename_start = quoted_filename.start('filename')
        extension_spans.add(
            (
                filename_start + filename_match.start(),
                filename_start + filename_match.end(),
            )
        )

    has_positive = bool(format_spans or extension_spans)
    first_json_start = min((match.start() for match in format_matches), default=-1)
    file_cue_before_json = bool(
        first_json_start > 0
        and _TEXT_ARTIFACT_FILE_CUE_RE.search(masked[:first_json_start])
    )
    response_format = bool(_JSON_TEXT_ARTIFACT_RESPONSE_FORMAT_RE.search(masked))
    negated_context = bool(_JSON_TEXT_ARTIFACT_NEGATED_CONTEXT_RE.search(masked))
    suppress_generic_fallback = bool(
        not has_positive
        and (
            negated_materialization
            or negated_context
            or quoted_json
            or (response_format and not file_cue_before_json)
        )
    )
    return _JsonTextArtifactIntent(
        format_spans=frozenset(format_spans),
        extension_spans=frozenset(extension_spans),
        suppress_generic_fallback=suppress_generic_fallback,
    )


def _text_artifact_format_match_has_distinct_artifact_cue(
    text: str,
    match: re.Match[str],
    *,
    json_intent: Optional[_JsonTextArtifactIntent] = None,
) -> bool:
    scope, _, _ = _text_artifact_match_scope(text, match.start(), match.end())
    raw_format = str(match.group('format') or '').strip().lower()
    extension = _normalize_text_artifact_extension(raw_format) or 'txt'
    if (
        extension in _TEXT_ARTIFACT_RESPONSE_FORMAT_ONLY_EXTENSIONS
        and (match.start(), match.end())
        not in (json_intent or _json_text_artifact_intent(text)).format_spans
    ):
        return False
    return bool(
        scope
        and _TEXT_ARTIFACT_ACTION_CUE_RE.search(scope)
        and _TEXT_ARTIFACT_DISTINCT_FORMAT_CUE_RE.search(scope)
    )


def _text_artifact_negation_match_is_cardinality_constraint(
    text: str,
    match: re.Match[str],
) -> bool:
    scope, _, _ = _text_artifact_match_scope(text, match.start(), match.end())
    if not scope:
        return False
    return bool(_TEXT_ARTIFACT_CARDINALITY_CONSTRAINT_RE.search(scope))


def _text_artifact_prompt_has_positive_request_outside_negation(
    text: str,
    matches: list[re.Match[str]],
) -> bool:
    masked = list(str(text or ''))
    for match in matches:
        if _text_artifact_negation_match_is_cardinality_constraint(text, match):
            _, start, end = _text_artifact_match_scope(text, match.start(), match.end())
        else:
            start, end = match.start(), match.end()
        for index in range(max(0, start), min(len(masked), end)):
            masked[index] = ' '
    remainder = ''.join(masked)
    return bool(
        _TEXT_ARTIFACT_FILE_CUE_RE.search(remainder)
        and _TEXT_ARTIFACT_ACTION_CUE_RE.search(remainder)
    ) or any(
        # A named creation command is affirmative file intent even without
        # the noun "file". Keep recognition separate from execution deferral;
        # the scope owner still enforces blanket/category/relative exclusions.
        # Reuse local polarity and literal boundaries, so an unrelated action
        # or a quoted example cannot supply the missing affirmative request.
        not _text_artifact_format_match_is_negated(remainder, filename)
        and not _json_text_artifact_span_is_inside_quoted_instruction(
            remainder, filename.start(), filename.end(),
        )
        and not negated
        and has_action
        for filename in _TEXT_ARTIFACT_EXTENSION_RE.finditer(remainder)
        for negated, has_action in [_json_text_artifact_candidate_state(
            remainder, filename.start(), filename.end(),
        )]
    )


def _text_artifact_prompt_is_negated(text: str) -> bool:
    # The broad exclusion matcher can cross a contrast ("do not generate
    # audio, but write a file"). Check the file cue's actual polarity before
    # treating that span as an instruction to suppress materialization.
    file_cues = list(_TEXT_ARTIFACT_FILE_CUE_RE.finditer(str(text or '')))
    matches = [
        match for match in _TEXT_ARTIFACT_NEGATION_RE.finditer(str(text or ''))
        if any(
            match.start() <= cue.start() < match.end()
            and _text_artifact_format_match_is_negated(text, cue)
            for cue in file_cues
        )
    ]
    if not matches:
        return False
    return not _text_artifact_prompt_has_positive_request_outside_negation(text, matches)


def _text_artifact_filename_match_is_validation_only(text: str, match: re.Match[str]) -> bool:
    prompt = str(text or '')
    clause, _, _ = _text_artifact_match_scope(prompt, match.start(), match.end())
    if not clause:
        return False
    if not _TEXT_ARTIFACT_MISSING_RE.search(clause):
        return False
    if _TEXT_ARTIFACT_ACTION_CUE_RE.search(clause):
        return False
    return bool(_TEXT_ARTIFACT_VALIDATION_ONLY_RE.search(clause))


def text_artifact_request_is_ungrounded_reference(prompt: str, *, source_available: bool = False) -> bool:
    text = str(prompt or '').strip()
    if not text or source_available or prompt_has_inline_text_artifact_source(text):
        return False
    if _json_text_artifact_intent(text).has_materialization:
        return False
    if _TEXT_ARTIFACT_SELF_CONTAINED_SOURCE_RE.search(text):
        return False
    if _TEXT_ARTIFACT_SAME_PROMPT_GENERATED_SOURCE_RE.search(text):
        return False
    if _TEXT_ARTIFACT_SELF_CONTAINED_CODE_BUNDLE_RE.search(text):
        return False
    extension_match = _TEXT_ARTIFACT_EXTENSION_RE.search(text)
    if extension_match and (
        _TEXT_ARTIFACT_FILE_CUE_RE.search(text)
        or _TEXT_ARTIFACT_ACTION_CUE_RE.search(text)
    ):
        return False
    reference_text = list(text)
    for match in _RELATIVE_ARTIFACT_CONTENT_THAT_RE.finditer(text):
        for index in range(match.start('relative'), match.end('relative')):
            reference_text[index] = ' '
    return bool(
        _TEXT_ARTIFACT_DEMONSTRATIVE_REFERENCE_RE.search(
            ''.join(reference_text)
        )
    )


def detect_text_artifact_request(
    prompt: str,
    *,
    source_available: bool = False,
    source_extension: Optional[str] = None,
    source_name: Optional[str] = None,
    source_path: Optional[str] = None,
) -> Optional[dict[str, str]]:
    """Detect explicit requests to materialize chat text as a file artifact."""

    requests = detect_text_artifact_requests(
        prompt,
        source_available=source_available,
        source_extension=source_extension,
        source_name=source_name,
        source_path=source_path,
    )
    return requests[0] if requests else None


def detect_text_artifact_requests(
    prompt: str,
    *,
    source_available: bool = False,
    source_extension: Optional[str] = None,
    source_name: Optional[str] = None,
    source_path: Optional[str] = None,
) -> list[dict[str, str]]:
    """Detect explicit requests to materialize one or more chat text file artifacts."""

    text = str(prompt or '').strip()
    if not text or _text_artifact_prompt_is_negated(text):
        return []
    json_intent = _json_text_artifact_intent(text)
    if text_artifact_request_is_ungrounded_reference(text, source_available=source_available):
        return []

    requests: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def append_request(request: dict[str, str]) -> None:
        extension = _normalize_text_artifact_extension(request.get('extension') or '')
        if not extension:
            return
        source_name = str(request.get('source_name') or '').strip() or f'generated-{extension}'
        source = str(request.get('source') or '').strip() or 'explicit_file_cue'
        key = (extension, source_name, source)
        if key in seen or any(
            item.get('extension') == extension
            and item.get('source_name') == source_name
            and item.get('source') == source
            for item in requests
        ):
            return
        if source == 'explicit_extension':
            for existing in requests:
                if existing.get('extension') == extension and existing.get('source') != 'explicit_extension':
                    existing['source'] = source
                    existing['source_name'] = source_name
                    seen.add(key)
                    return
        elif source == 'selected_source_edit':
            for existing in requests:
                if (
                    existing.get('extension') == extension
                    and existing.get('source_name') == source_name
                ):
                    existing.update(
                        {
                            'source': source,
                            'source_name': source_name,
                            **(
                                {'target_path': str(request.get('target_path') or '').strip()}
                                if str(request.get('target_path') or '').strip()
                                else {}
                            ),
                        }
                    )
                    seen.add(key)
                    return
        elif (
            source != 'each_part_file_cue'
            and any(item.get('extension') == extension for item in requests)
        ):
            return
        seen.add(key)
        normalized_request = {
            'extension': extension,
            'source': source,
            'source_name': source_name,
        }
        target_path = str(request.get('target_path') or '').strip()
        if target_path:
            normalized_request['target_path'] = target_path
        requests.append(normalized_request)

    def has_request_extension(extension: str) -> bool:
        normalized_extension = _normalize_text_artifact_extension(extension or '')
        return bool(
            normalized_extension
            and any(item.get('extension') == normalized_extension for item in requests)
        )

    has_file_cue = bool(_TEXT_ARTIFACT_FILE_CUE_RE.search(text))
    has_action_cue = any(
        not _text_artifact_format_match_is_negated(text, match)
        and not _json_text_artifact_span_is_inside_quoted_instruction(
            text, match.start(), match.end(),
        )
        for match in _TEXT_ARTIFACT_ACTION_CUE_RE.finditer(text)
    )
    has_web_page_need_cue = bool(_TEXT_ARTIFACT_WEB_PAGE_NEED_CUE_RE.search(text))
    # A web possibility cannot borrow an action from an unrelated sentence
    # (for example, "create an image ... keep website ideas reserved").
    has_implicit_web_page_cue = any(
        not _text_artifact_format_match_is_negated(text, match)
        and not _TEXT_ARTIFACT_RESERVED_SUFFIX_RE.search(text[match.end():])
        and bool(
            _TEXT_ARTIFACT_ACTION_CUE_RE.search(scope)
            or _TEXT_ARTIFACT_WEB_PAGE_NEED_CUE_RE.search(scope)
        )
        for match in _TEXT_ARTIFACT_IMPLICIT_WEB_PAGE_RE.finditer(text)
        for scope, _, _ in [_text_artifact_match_scope(text, match.start(), match.end())]
    )
    has_bare_german_page_with_generated_visuals = bool(
        _TEXT_ARTIFACT_BARE_GERMAN_PAGE_RE.search(text)
        and _TEXT_ARTIFACT_GENERATED_VISUAL_CONTEXT_RE.search(text)
    )
    format_matches = [
        match for match in _TEXT_ARTIFACT_FORMAT_RE.finditer(text)
        if not _text_artifact_format_is_embedded(text, match)
    ]
    distinct_format_match_spans = {
        (format_match.start(), format_match.end())
        for format_match in format_matches
        if _text_artifact_format_match_has_distinct_artifact_cue(
            text,
            format_match,
            json_intent=json_intent,
        )
    }
    has_explicit_format_file_cue = has_file_cue and has_action_cue
    explicit_svg_request_spans = explicit_svg_artifact_request_spans(text)
    explicit_format_file_match_spans = {
        (format_match.start(), format_match.end())
        for format_match in format_matches
        if (
            (
                (_normalize_text_artifact_extension(format_match.group('format') or '') or 'txt')
                in _TEXT_ARTIFACT_RESPONSE_FORMAT_ONLY_EXTENSIONS
                and (format_match.start(), format_match.end()) in json_intent.format_spans
            )
            or (
                has_explicit_format_file_cue
                and (
                    (_normalize_text_artifact_extension(format_match.group('format') or '') or 'txt')
                    not in _TEXT_ARTIFACT_RESPONSE_FORMAT_ONLY_EXTENSIONS
                )
            )
            or (
                _normalize_text_artifact_extension(format_match.group('format') or '') == 'svg'
                and any(
                    start <= format_match.start() and format_match.end() <= end
                    for start, end in explicit_svg_request_spans
                )
            )
        )
    }

    if explicit_format_file_match_spans or distinct_format_match_spans:
        each_part_count = _text_artifact_each_part_count(text)
        if explicit_format_file_match_spans and each_part_count > 1:
            for format_match in format_matches:
                if _text_artifact_format_match_is_negated(text, format_match):
                    continue
                if (
                    (format_match.start(), format_match.end())
                    not in explicit_format_file_match_spans
                ):
                    continue
                raw_format = str(format_match.group('format') or '').strip().lower()
                extension = _normalize_text_artifact_extension(raw_format) or 'txt'
                for index in range(1, each_part_count + 1):
                    append_request(
                        {
                            'extension': extension,
                            'source': 'each_part_file_cue',
                            'source_name': f'generated-{extension}-part-{index}',
                        }
                    )
                if requests:
                    return requests
        for format_match in format_matches:
            if _text_artifact_format_match_is_negated(text, format_match):
                continue
            match_span = (format_match.start(), format_match.end())
            has_explicit_match_cue = match_span in explicit_format_file_match_spans
            if not has_explicit_match_cue and match_span not in distinct_format_match_spans:
                continue
            raw_format = str(format_match.group('format') or '').strip().lower()
            extension = _normalize_text_artifact_extension(raw_format) or 'txt'
            if has_request_extension(extension):
                continue
            append_request(
                {
                    'extension': extension,
                    'source': (
                        'explicit_format_file_cue'
                        if has_explicit_match_cue
                        else 'distinct_format_artifact_cue'
                    ),
                    'source_name': 'README' if raw_format == 'readme' else f'generated-{extension}',
                }
            )

    if has_file_cue or has_action_cue:
        for extension_match in _TEXT_ARTIFACT_EXTENSION_RE.finditer(text):
            if _text_artifact_format_match_is_negated(text, extension_match):
                continue
            if _text_artifact_filename_match_is_validation_only(text, extension_match):
                continue
            extension = _normalize_text_artifact_extension(extension_match.group('ext') or '')
            if (
                extension == 'json'
                and (extension_match.start(), extension_match.end())
                not in json_intent.extension_spans
            ):
                continue
            if extension:
                append_request(
                    {
                        'extension': extension,
                        'source': 'explicit_extension',
                        'source_name': extension_match.group('name') or f'generated-{extension}',
                    }
                )

    if (
        (has_action_cue or has_web_page_need_cue)
        and not has_request_extension('html')
        and (has_implicit_web_page_cue or has_bare_german_page_with_generated_visuals)
    ):
        append_request(
            {
                'extension': 'html',
                'source': 'implicit_web_page_cue',
                'source_name': 'generated-html',
            }
        )

    source_artifact_extension = _normalize_text_artifact_extension(source_extension or '')
    if (
        source_available
        and source_artifact_extension
        and _text_artifact_selected_source_edit_is_bound(
            text,
            source_extension=source_artifact_extension,
            source_name=source_name,
            response_json_only=json_intent.suppress_generic_fallback,
        )
    ):
        append_request(
            {
                'extension': source_artifact_extension,
                'source': 'selected_source_edit',
                'source_name': str(source_name or '').strip() or f'updated-{source_artifact_extension}',
                **(
                    {'target_path': str(source_path or '').strip()}
                    if str(source_path or '').strip()
                    else {}
                ),
            }
        )
        return requests

    if not (has_file_cue and has_action_cue):
        return requests
    if requests:
        return requests
    if json_intent.suppress_generic_fallback:
        return requests
    # "Saved" evidence describes a predecessor. It cannot by itself request
    # an unspecified new text file, even alongside another affirmative action.
    if not _TEXT_ARTIFACT_GENERIC_FALLBACK_CUE_RE.search(text):
        return requests

    append_request({'extension': 'txt', 'source': 'explicit_file_cue', 'source_name': 'generated-text'})
    return requests


def generated_text_is_artifact_self_claim(content: str) -> bool:
    """Return true when text only claims an artifact instead of being the artifact content."""

    return bool(_TEXT_ARTIFACT_SELF_CLAIM_RE.search(str(content or '').strip()))


def generated_text_blocks_artifact_persistence(content: str) -> bool:
    return bool(_TEXT_ARTIFACT_BLOCKED_CONTENT_RE.search(str(content or '').strip()))


def _code_block_language_matches_extension(language: str, extension: str) -> bool:
    if not _text_artifact_block_language_is_payload(language):
        return False
    lang = _normalize_text_artifact_block_language(language)
    ext = _normalize_text_artifact_extension(extension or '') or 'txt'
    aliases = {
        'md': {'md', 'markdown'},
        'html': {'html', 'htm'},
        'css': {'css'},
        'js': {'js', 'javascript', 'mjs', 'cjs'},
        'ts': {'ts', 'typescript'},
        'tsx': {'tsx'},
        'jsx': {'jsx'},
        'json': {'json'},
        'yaml': {'yaml', 'yml'},
        'yml': {'yaml', 'yml'},
        'xml': {'xml'},
        'csv': {'csv'},
        'svg': {'svg', 'xml'},
        'py': {'py', 'python'},
        'sh': {'sh', 'bash', 'shell'},
        'sql': {'sql'},
        'txt': {'txt', 'text', ''},
    }
    return lang in aliases.get(ext, {ext, ''})


def _parse_text_artifact_tag_attrs(raw_attrs: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in _TEXT_ARTIFACT_TAG_ATTR_RE.finditer(str(raw_attrs or '')):
        name = str(match.group('name') or '').strip().lower()
        value = str(match.group('value') or '').strip()
        if name and value:
            attrs[name] = value
    return attrs


def _text_artifact_tag_extension(attrs: dict[str, str]) -> Optional[str]:
    identifier = str(
        attrs.get('identifier')
        or attrs.get('filename')
        or attrs.get('file')
        or attrs.get('name')
        or ''
    ).strip()
    if identifier:
        extension = _normalize_text_artifact_extension(Path(identifier).suffix)
        if extension:
            return extension
    raw_type = str(attrs.get('type') or attrs.get('mime') or attrs.get('mime_type') or '').strip().lower()
    if raw_type:
        if '/' in raw_type:
            extension = _normalize_text_artifact_extension(raw_type.rsplit('/', 1)[-1])
            if extension:
                return extension
        extension = _normalize_text_artifact_extension(raw_type)
        if extension:
            return extension
    return None


def _text_artifact_tag_source_name(attrs: dict[str, str], extension: str) -> str:
    identifier = str(
        attrs.get('identifier')
        or attrs.get('filename')
        or attrs.get('file')
        or attrs.get('name')
        or attrs.get('title')
        or ''
    ).strip()
    if identifier:
        stem = Path(identifier).stem
        if stem:
            return stem
    return f'generated-{extension or "text"}'


def text_artifact_request_is_generic(artifact_request: Mapping[str, Any]) -> bool:
    """Only an admitted unspecified save permits provider binding derivation."""
    return bool(
        artifact_request.get('source') == 'explicit_file_cue'
        and artifact_request.get('extension') == 'txt'
        and artifact_request.get('source_name') in (None, '', 'generated-text')
        and not artifact_request.get('target_path')
    )


def _artifact_request_with_tag_metadata(
    artifact_request: dict[str, str],
    *,
    tag_extension: Optional[str],
    tag_source_name: Optional[str],
) -> dict[str, str]:
    request = dict(artifact_request or {})
    normalized_tag_extension = _normalize_text_artifact_extension(tag_extension or '')
    request_extension = _normalize_text_artifact_extension(request.get('extension') or '') or 'txt'
    generic = text_artifact_request_is_generic(request)
    if normalized_tag_extension and generic:
        request['extension'] = normalized_tag_extension
        request['source'] = 'artifact_tag'
    elif normalized_tag_extension:
        request['extension'] = request_extension
    else:
        request['extension'] = request_extension
    if normalized_tag_extension and generic and (
        not str(request.get('source_name') or '').strip()
        or str(request.get('source_name') or '').strip() == 'generated-text'
    ):
        request['source_name'] = str(tag_source_name or '').strip() or f'generated-{normalized_tag_extension}'
    return request


def _artifact_request_with_code_block_metadata(
    artifact_request: dict[str, str],
    *,
    block_extension: Optional[str],
) -> dict[str, str]:
    request = dict(artifact_request or {})
    normalized_block_extension = _normalize_text_artifact_extension(block_extension or '')
    request_extension = _normalize_text_artifact_extension(request.get('extension') or '') or 'txt'
    if normalized_block_extension and text_artifact_request_is_generic(request):
        request['extension'] = normalized_block_extension
        request['source'] = 'code_block'
        if (
            not str(request.get('source_name') or '').strip()
            or str(request.get('source_name') or '').strip() == 'generated-text'
        ):
            request['source_name'] = f'generated-{normalized_block_extension}'
    else:
        request['extension'] = request_extension
    return request


def _looks_like_raw_artifact_payload(content: str, extension: str) -> bool:
    text = str(content or '').strip()
    ext = _normalize_text_artifact_extension(extension or '') or 'txt'
    if not text:
        return False
    if ext in {'html', 'htm'}:
        return bool(re.search(r'(?is)^\s*(?:<!doctype\s+html\b|<html\b|<[a-z][\w:-]*(?:\s|>|/))', text))
    if ext == 'svg':
        return bool(re.search(r'(?is)^\s*<svg\b', text))
    if ext == 'css':
        return bool(re.search(r'(?s)[{};]', text))
    if ext in {'js', 'mjs', 'cjs', 'ts', 'tsx', 'jsx'}:
        return bool(re.search(r'(?m)^\s*(?:import|export|const|let|var|function|class|interface|type)\b', text))
    if ext == 'json':
        return text.startswith(('{', '['))
    if ext in {'yaml', 'yml'}:
        return bool(re.search(r'(?m)^\s*[-\w]+\s*:', text))
    if ext == 'xml':
        return text.startswith('<?xml') or bool(re.search(r'(?s)^\s*<[A-Za-z_][\w:.-]*(?:\s|>|/)', text))
    if ext == 'csv':
        return ',' in text and '\n' in text
    if ext in {'py', 'sh', 'sql'}:
        return bool(re.search(r'(?m)^\s*(?:def |class |import |from |#!|SELECT |CREATE |INSERT |UPDATE |DELETE )', text, re.IGNORECASE))
    return True


def _typed_text_artifact_payload_is_plausible(content: str, extension: str) -> bool:
    ext = _normalize_text_artifact_extension(extension or '') or 'txt'
    if text_artifact_content_is_materializer_instruction_echo(content):
        return False
    if ext in {'txt', 'md', 'markdown'}:
        return True
    return _looks_like_raw_artifact_payload(content, ext)


def _json_text_artifact_value_has_control_shape(value: Any) -> bool:
    if isinstance(value, list):
        return any(_json_text_artifact_value_has_control_shape(item) for item in value)
    if not isinstance(value, dict):
        return False
    normalized = {
        str(key or '').strip().lower(): child
        for key, child in value.items()
        if str(key or '').strip()
    }
    if set(normalized).intersection(_TEXT_ARTIFACT_CONTROL_JSON_KEYS):
        return True
    return any(
        _json_text_artifact_value_has_control_shape(child)
        for child in normalized.values()
        if isinstance(child, (dict, list))
    )


def _json_text_artifact_wrapper_candidates(text: str) -> list[Any]:
    candidates: list[Any] = []
    raw_text = str(text or '').strip()
    if raw_text:
        candidates.append(raw_text)
    for match in _TEXT_ARTIFACT_FENCED_BLOCK_RE.finditer(raw_text):
        language = _normalize_text_artifact_block_language(match.group('lang') or '')
        if language == 'json':
            body = (match.group('body') or '').strip()
            if body:
                candidates.append(body)

    parsed: list[Any] = []
    for candidate in candidates:
        try:
            parsed.append(json.loads(candidate))
        except (TypeError, ValueError):
            continue
    return parsed


def _json_text_artifact_obligations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    raw_obligations = value.get('output_obligations')
    if raw_obligations is None and isinstance(value.get('request_ir'), dict):
        raw_obligations = value['request_ir'].get('output_obligations')
    if raw_obligations is None and isinstance(value.get('payload'), dict):
        raw_obligations = value['payload'].get('output_obligations')
    if not isinstance(raw_obligations, list):
        return []
    return [item for item in raw_obligations if isinstance(item, dict)]


def _json_text_artifact_obligation_extension(obligation: dict[str, Any]) -> Optional[str]:
    name = str(
        obligation.get('name')
        or obligation.get('filename')
        or obligation.get('file')
        or obligation.get('identifier')
        or ''
    ).strip()
    if name:
        extension = _normalize_text_artifact_extension(Path(name).suffix)
        if extension:
            return extension
    raw_type = str(
        obligation.get('mime_type')
        or obligation.get('mime')
        or obligation.get('type')
        or ''
    ).strip().lower()
    if raw_type:
        if raw_type.startswith('text/'):
            extension = _normalize_text_artifact_extension(raw_type.rsplit('/', 1)[-1])
            if extension:
                return extension
        extension = _normalize_text_artifact_extension(raw_type)
        if extension:
            return extension
    return None


def _json_text_artifact_obligation_source_name(
    obligation: dict[str, Any],
    extension: str,
) -> str:
    name = str(
        obligation.get('name')
        or obligation.get('filename')
        or obligation.get('file')
        or obligation.get('identifier')
        or obligation.get('title')
        or ''
    ).strip()
    if name:
        stem = Path(name).stem
        if stem:
            return stem
    return f'generated-{extension or "text"}'


def _json_text_artifact_content_payload_is_safe(content: str, extension: str) -> bool:
    text = str(content or '').strip()
    ext = _normalize_text_artifact_extension(extension or '') or 'txt'
    if not text or text_artifact_content_is_materializer_instruction_echo(text) or ext == 'txt':
        return False
    if ext in {'md', 'markdown'}:
        return bool(re.search(r'(?m)^\s*(?:#|[-*]\s+|```|\|)', text))
    if ext == 'json' and _json_text_artifact_control_wrapper_without_payload(text):
        return False
    return _looks_like_raw_artifact_payload(text, ext)


def _json_text_artifact_obligation_content(
    obligation: dict[str, Any],
    *,
    request_extension: str,
) -> Optional[str]:
    extension = _json_text_artifact_obligation_extension(obligation) or request_extension
    normalized_extension = _normalize_text_artifact_extension(extension or '') or 'txt'

    def safe_payload(value: Any) -> Optional[str]:
        if not isinstance(value, str) or not value.strip():
            return None
        text = value.strip()
        if text_artifact_content_is_materializer_instruction_echo(text):
            return None
        if normalized_extension == 'txt':
            return text
        if not _json_text_artifact_content_payload_is_safe(text, normalized_extension):
            return None
        return text

    content = safe_payload(obligation.get('content'))
    if content:
        return content
    content_payload = safe_payload(obligation.get('content_payload'))
    if not content_payload:
        return None
    return content_payload.strip()


def _json_text_artifact_control_wrapper_without_payload(text: str) -> bool:
    parsed_candidates = _json_text_artifact_wrapper_candidates(text)
    for candidate in parsed_candidates:
        if not _json_text_artifact_value_has_control_shape(candidate):
            continue
        obligations = _json_text_artifact_obligations(candidate)
        for obligation in obligations:
            extension = _json_text_artifact_obligation_extension(obligation) or 'txt'
            if _json_text_artifact_obligation_content(
                obligation,
                request_extension=extension,
            ):
                return False
        return True
    return False


def _artifact_request_with_json_obligation_metadata(
    artifact_request: dict[str, str],
    *,
    obligation: dict[str, Any],
) -> dict[str, str]:
    request = dict(artifact_request or {})
    request_extension = _normalize_text_artifact_extension(request.get('extension') or '') or 'txt'
    obligation_extension = _json_text_artifact_obligation_extension(obligation)
    generic = text_artifact_request_is_generic(request)
    if obligation_extension and generic:
        request['extension'] = obligation_extension
    else:
        request['extension'] = request_extension
    if generic and (
        not str(request.get('source_name') or '').strip()
        or str(request.get('source_name') or '').strip() == 'generated-text'
    ):
        request['source_name'] = _json_text_artifact_obligation_source_name(
            obligation,
            request.get('extension') or request_extension,
        )
    request['source'] = 'json_output_obligation'
    return request


def _json_text_artifact_payloads(
    text: str,
    requests: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if not requests:
        return []
    parsed_candidates = _json_text_artifact_wrapper_candidates(text)
    if not parsed_candidates:
        return []

    obligations: list[dict[str, Any]] = []
    for candidate in parsed_candidates:
        obligations.extend(_json_text_artifact_obligations(candidate))
    if not obligations:
        return []

    used_obligations: set[int] = set()
    payloads: list[dict[str, Any]] = []
    for request in requests:
        request_extension = _normalize_text_artifact_extension(request.get('extension') or '') or 'txt'
        matching: list[tuple[int, dict[str, Any]]] = []
        generic: list[tuple[int, dict[str, Any]]] = []
        for index, obligation in enumerate(obligations):
            if index in used_obligations:
                continue
            content = _json_text_artifact_obligation_content(
                obligation,
                request_extension=request_extension,
            )
            if not content:
                continue
            obligation_extension = _json_text_artifact_obligation_extension(obligation)
            if (
                obligation_extension
                and request_extension != 'txt'
                and obligation_extension == request_extension
            ):
                matching.append((index, obligation))
            elif request_extension == 'txt' or not obligation_extension:
                generic.append((index, obligation))
        selected = matching[0] if matching else (generic[0] if generic else None)
        if not selected:
            continue
        index, obligation = selected
        used_obligations.add(index)
        payloads.append(
            {
                'artifact_request': _artifact_request_with_json_obligation_metadata(
                    request,
                    obligation=obligation,
                ),
                'content': str(
                    _json_text_artifact_obligation_content(
                        obligation,
                        request_extension=request_extension,
                    )
                    or ''
                ).strip(),
            }
        )
    return payloads


def extract_text_artifact_payload(content: str, artifact_request: Optional[dict[str, str]]) -> Optional[str]:
    """Return the exact file payload to persist, or None when no truthful payload exists."""

    payloads = extract_text_artifact_payloads(content, [artifact_request] if artifact_request else [])
    return str(payloads[0].get('content') or '') if payloads else None


def extract_text_artifact_payloads(
    content: str,
    artifact_requests: Optional[list[dict[str, str]]],
) -> list[dict[str, Any]]:
    """Return exact file payloads to persist for each requested text artifact."""

    text = str(content or '').strip()
    requests = [item for item in (artifact_requests or []) if isinstance(item, dict)]
    if not text or not requests:
        return []
    blocks = [
        {
            'index': index,
            'language': match.group('lang') or '',
            'extension': _text_artifact_block_extension(match.group('lang') or ''),
            'is_payload': _text_artifact_block_language_is_payload(match.group('lang') or ''),
            'is_control_json': (
                _normalize_text_artifact_block_language(match.group('lang') or '') == 'json'
                and _json_text_artifact_control_wrapper_without_payload((match.group('body') or '').strip())
            ),
            'body': (match.group('body') or '').strip(),
        }
        for index, match in enumerate(_TEXT_ARTIFACT_FENCED_BLOCK_RE.finditer(text))
        if (match.group('body') or '').strip()
    ]
    artifact_tags = []
    for index, match in enumerate(_TEXT_ARTIFACT_TAG_RE.finditer(text)):
        body = (match.group('body') or '').strip()
        if not body:
            continue
        attrs = _parse_text_artifact_tag_attrs(match.group('attrs') or '')
        tag_extension = _text_artifact_tag_extension(attrs)
        artifact_tags.append(
            {
                'index': index,
                'attrs': attrs,
                'extension': tag_extension,
                'source_name': _text_artifact_tag_source_name(attrs, tag_extension or 'txt'),
                'body': body,
            }
        )
    used_blocks: set[int] = set()
    used_tags: set[int] = set()
    fulfilled_request_indexes: set[int] = set()
    payloads: list[dict[str, Any]] = []

    for request_index, request in enumerate(requests):
        extension = request.get('extension') or 'txt'
        matching_blocks = [
            block for block in blocks
            if block['index'] not in used_blocks
            and block.get('is_payload') is not False
            and not block.get('is_control_json')
            and _code_block_language_matches_extension(str(block.get('language') or ''), extension)
            and _typed_text_artifact_payload_is_plausible(str(block.get('body') or ''), extension)
        ]
        if matching_blocks:
            block = matching_blocks[0]
            used_blocks.add(int(block['index']))
            fulfilled_request_indexes.add(request_index)
            payloads.append({'artifact_request': request, 'content': str(block.get('body') or '')})
            continue

        matching_tags = [
            tag for tag in artifact_tags
            if tag['index'] not in used_tags
            and (
                _normalize_text_artifact_extension(str(tag.get('extension') or '')) == _normalize_text_artifact_extension(extension or '')
                or _normalize_text_artifact_extension(extension or '') == 'txt'
            )
            and _typed_text_artifact_payload_is_plausible(str(tag.get('body') or ''), extension)
        ]
        if matching_tags:
            tag = matching_tags[0]
            used_tags.add(int(tag['index']))
            request_with_tag = _artifact_request_with_tag_metadata(
                request,
                tag_extension=str(tag.get('extension') or ''),
                tag_source_name=str(tag.get('source_name') or ''),
            )
            fulfilled_request_indexes.add(request_index)
            payloads.append({'artifact_request': request_with_tag, 'content': str(tag.get('body') or '')})
            continue

    remaining_requests = [
        request for request_index, request in enumerate(requests)
        if request_index not in fulfilled_request_indexes
    ]
    json_payloads = _json_text_artifact_payloads(text, remaining_requests)
    if json_payloads:
        return payloads + json_payloads

    for request_index, request in enumerate(requests):
        if request_index in fulfilled_request_indexes:
            continue
        extension = request.get('extension') or 'txt'
        if blocks and _normalize_text_artifact_extension(extension or '') in {'txt', 'md'}:
            concrete_blocks = [
                block for block in blocks
                if block['index'] not in used_blocks
                and block.get('is_payload') is not False
                and not block.get('is_control_json')
                and _normalize_text_artifact_extension(str(block.get('extension') or ''))
                and _typed_text_artifact_payload_is_plausible(str(block.get('body') or ''), str(block.get('extension') or extension))
            ]
            if concrete_blocks:
                block = concrete_blocks[0]
                used_blocks.add(int(block['index']))
                fulfilled_request_indexes.add(request_index)
                request_with_block = _artifact_request_with_code_block_metadata(
                    request,
                    block_extension=str(block.get('extension') or ''),
                )
                payloads.append({'artifact_request': request_with_block, 'content': str(block.get('body') or '')})
                continue
            available = [
                block for block in blocks
                if block['index'] not in used_blocks
                and block.get('is_payload') is not False
                and not block.get('is_control_json')
                and _typed_text_artifact_payload_is_plausible(str(block.get('body') or ''), extension)
            ]
            if available:
                block = available[0]
                used_blocks.add(int(block['index']))
                fulfilled_request_indexes.add(request_index)
                payloads.append({'artifact_request': request, 'content': str(block.get('body') or '')})
                continue

    if payloads:
        return payloads

    if len(requests) != 1:
        return []
    artifact_request = requests[0]
    extension = artifact_request.get('extension') or 'txt'
    raw_blocks = [
        (match.group('lang') or '', (match.group('body') or '').strip())
        for match in _TEXT_ARTIFACT_FENCED_BLOCK_RE.finditer(text)
        if (match.group('body') or '').strip()
        and _text_artifact_block_language_is_payload(match.group('lang') or '')
        and not (
            _normalize_text_artifact_block_language(match.group('lang') or '') == 'json'
            and _json_text_artifact_control_wrapper_without_payload((match.group('body') or '').strip())
        )
    ]
    matching_raw_blocks = [
        body for language, body in raw_blocks
        if _code_block_language_matches_extension(language, extension)
        and _typed_text_artifact_payload_is_plausible(body, extension)
    ]
    if matching_raw_blocks:
        return [{'artifact_request': artifact_request, 'content': max(matching_raw_blocks, key=len)}]
    matching_raw_tags = [
        tag for tag in artifact_tags
        if (
            _normalize_text_artifact_extension(str(tag.get('extension') or '')) == _normalize_text_artifact_extension(extension or '')
            or _normalize_text_artifact_extension(extension or '') == 'txt'
        )
        and _typed_text_artifact_payload_is_plausible(str(tag.get('body') or ''), extension)
    ]
    if matching_raw_tags:
        tag = matching_raw_tags[0]
        request_with_tag = _artifact_request_with_tag_metadata(
            artifact_request,
            tag_extension=str(tag.get('extension') or ''),
            tag_source_name=str(tag.get('source_name') or ''),
        )
        return [{'artifact_request': request_with_tag, 'content': str(tag.get('body') or '')}]
    json_payloads = _json_text_artifact_payloads(text, [artifact_request])
    if json_payloads:
        return json_payloads
    if raw_blocks and _normalize_text_artifact_extension(extension or '') in {'txt', 'md'}:
        concrete_raw_blocks = [
            (language, body)
            for language, body in raw_blocks
            if _text_artifact_block_extension(language)
            and _typed_text_artifact_payload_is_plausible(body, _text_artifact_block_extension(language))
        ]
        if concrete_raw_blocks:
            language, body = max(concrete_raw_blocks, key=lambda item: len(item[1]))
            request_with_block = _artifact_request_with_code_block_metadata(
                artifact_request,
                block_extension=_text_artifact_block_extension(language),
            )
            return [{'artifact_request': request_with_block, 'content': body}]
        return [{'artifact_request': artifact_request, 'content': max((body for _language, body in raw_blocks), key=len)}]
    if generated_text_blocks_artifact_persistence(text):
        return []
    if generated_text_is_artifact_self_claim(text):
        return []
    if _json_text_artifact_control_wrapper_without_payload(text):
        return []
    if _typed_text_artifact_payload_is_plausible(text, extension):
        return [{'artifact_request': artifact_request, 'content': text}]
    return []


