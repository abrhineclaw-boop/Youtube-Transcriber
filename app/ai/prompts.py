"""Prompt templates for analysis packages and individual analyses.

Package prompts bundle multiple analyses into a single API call to reduce costs.
Profile context is injected into prompts so the AI interprets content
structure appropriately for the content type.
"""


# --- Package A: Full Scan (automatic) ---
def package_a_prompt(profile_name: str, profile_hints: str) -> str:
    return f"""You are analyzing a {profile_name} transcript. {profile_hints}

Perform ALL of the following analyses in a single pass. Return a JSON object with a key for each analysis.

## 1. BASELINE (key: "baseline")
Identify the major sections of this content. For each section, provide a title, start/end timestamps (seconds), a one-sentence description, and a detailed summary (3-5 sentences covering the key points, arguments, and takeaways of that section). Also write a concise overall summary (3-5 sentences) and generate 3-5 short lowercase topic tags.

## 2. CONTENT VS FLUFF (key: "content_vs_fluff")
Map which parts are substantive vs filler (intros, outros, sponsor reads, tangents, repetition). For each segment, classify as "substance" or "filler" with timestamps. Provide optimal start/stop timestamps and substance/filler percentages.

## 3. NAMED ENTITIES (key: "named_entities")
Extract all people, companies, products, technologies, places, and other named entities mentioned. Include the entity type, first mention timestamp, and brief context.

## 4. INFO DENSITY (key: "info_density")
Score each section identified in the baseline by information value per minute (0-100). Briefly justify each score.

## 5. EXECUTIVE BRIEFING (key: "executive_briefing")
Write 3-5 bullet points capturing what someone needs to know from this content. Each bullet should be a concise, self-contained insight. This is the "too long; didn't watch" version.

## 6. CONCEPT MAP (key: "concept_map")
Create a concept map capturing the transcript's structure as a radial tree. The central_node is the overall topic, branches are major themes, and children are specific points under each theme. Aim for 3-6 branches with 2-4 children each.

Return your response as valid JSON with this exact structure:
{{
  "baseline": {{
    "outline": [
      {{"title": "Section Title", "start_time": 0, "end_time": 120, "description": "Brief description", "summary": "Detailed 3-5 sentence summary of this section covering key points and takeaways."}}
    ],
    "summary": "Overall summary text.",
    "tags": ["tag1", "tag2", "tag3"]
  }},
  "content_vs_fluff": {{
    "segments": [
      {{"start_time": 0, "end_time": 60, "type": "filler", "label": "Intro", "description": "Host introduces themselves"}}
    ],
    "optimal_start": 65,
    "optimal_end": 3400,
    "substance_percentage": 75,
    "filler_percentage": 25,
    "summary": "Brief description of content distribution"
  }},
  "named_entities": [
    {{"name": "Entity Name", "type": "person", "first_mention_timestamp": 45, "context": "Why mentioned"}}
  ],
  "info_density": [
    {{"section_title": "Section Title", "score": 72, "justification": "Why this score"}}
  ],
  "executive_briefing": ["Key insight or takeaway 1", "Key insight or takeaway 2", "Key insight or takeaway 3"],
  "concept_map": {{
    "central_node": "Overall topic of the transcript",
    "branches": [
      {{
        "label": "Major theme",
        "importance": 0.8,
        "relationship_type": "supports",
        "children": [
          {{
            "label": "Specific point",
            "importance": 0.6,
            "detail": "One-sentence elaboration"
          }}
        ]
      }}
    ]
  }}
}}

Return ONLY the JSON, no markdown fences or additional text."""


# --- Package B: Deep Extraction (on-demand) ---
def package_b_prompt(profile_name: str, profile_hints: str) -> str:
    return f"""You are analyzing a {profile_name} transcript. {profile_hints}

Perform ALL of the following analyses in a single pass. Return a JSON object with a key for each analysis.

## 1. SECTION SUMMARIES (key: "section_summaries")
For each section in the transcript, generate a concise summary (2-4 sentences) and list 2-4 key points.

## 2. QUOTE & CLAIM EXTRACTION (key: "quote_extraction")
Extract notable quotes, specific claims, statistics, and attributable statements. Include exact text, speaker, timestamp, category (quote/claim/statistic/insight), and context.

## 3. ARGUMENT MAPPING (key: "argument_mapping")
Identify the main arguments or claims made in the content. For each, list the supporting evidence, describe the logical structure, and rate argument strength (strong/moderate/weak).

## 4. CREDIBILITY FLAGS (key: "credibility_flags")
Flag unsupported claims, hedging language, contradictions, missing citations, and any credibility concerns. Rate severity as low/medium/high.

Return your response as valid JSON with this exact structure:
{{
  "section_summaries": [
    {{"section_title": "Title", "summary": "Summary text", "key_points": ["point 1", "point 2"]}}
  ],
  "quote_extraction": {{
    "extractions": [
      {{"text": "Exact quote", "speaker": "Speaker", "timestamp": 245, "category": "quote", "context": "Why notable"}}
    ],
    "summary": "Overview of significant findings"
  }},
  "argument_mapping": {{
    "arguments": [
      {{
        "claim": "The main claim",
        "evidence": ["Evidence point 1", "Evidence point 2"],
        "logical_structure": "How the argument is built",
        "strength": "strong"
      }}
    ],
    "summary": "Overview of argumentative structure"
  }},
  "credibility_flags": {{
    "flags": [
      {{"type": "unsupported_claim", "description": "What the issue is", "timestamp": 300, "severity": "medium"}}
    ],
    "summary": "Overall credibility assessment"
  }}
}}

Return ONLY the JSON, no markdown fences or additional text."""


# --- Package C: Research Scan (on-demand) ---
def package_c_prompt(profile_name: str, profile_hints: str) -> str:
    return f"""You are analyzing a {profile_name} transcript. {profile_hints}

Perform ALL of the following analyses in a single pass. Return a JSON object with a key for each analysis.

## 1. QUESTION EXTRACTION (key: "question_extraction")
Extract all questions asked during the video — by the host, guests, or audience. Include the question text, who asked it, the timestamp, and context.

## 2. RESOURCE & REFERENCE EXTRACTION (key: "resource_extraction")
Extract all resources mentioned: URLs, book titles, tools, software, papers, people to follow, and other references. Categorize each (book/url/tool/paper/person/other) and include context for why it was mentioned.

## 3. NOVELTY SCORING (key: "novelty_scoring")
For each major topic discussed, score how novel/original the content is (0-100). Is this saying something new, or rehashing common knowledge? Include an overall novelty score.

Return your response as valid JSON with this exact structure:
{{
  "question_extraction": {{
    "questions": [
      {{"text": "The question asked", "speaker": "Who asked", "timestamp": 120, "context": "Why asked"}}
    ]
  }},
  "resource_extraction": {{
    "resources": [
      {{"name": "Resource name", "type": "book", "context": "Why mentioned", "timestamp": 450}}
    ]
  }},
  "novelty_scoring": {{
    "topics": [
      {{"topic": "Topic name", "score": 65, "justification": "Why this score"}}
    ],
    "overall_score": 58,
    "summary": "Assessment of content originality"
  }}
}}

Return ONLY the JSON, no markdown fences or additional text."""


# --- Section Deep-Dive (standalone, per-section) ---
def section_deep_dive_prompt(profile_name: str, profile_hints: str, section_title: str) -> str:
    return f"""You are doing a deep analysis of one specific section from a {profile_name} transcript. {profile_hints}

The section is titled: "{section_title}"

Provide a thorough analysis of this section:
1. Detailed summary (4-6 sentences)
2. All key points and takeaways
3. Notable quotes or claims with timestamps
4. Questions raised or left unanswered
5. Connections to other topics mentioned

Return your response as valid JSON with this exact structure:
{{
  "section_title": "{section_title}",
  "detailed_summary": "Thorough 4-6 sentence summary",
  "key_points": ["point 1", "point 2"],
  "notable_quotes": [
    {{"text": "Quote text", "timestamp": 120, "significance": "Why notable"}}
  ],
  "questions": ["Question 1", "Question 2"],
  "connections": ["Connection to other topic 1"]
}}

Return ONLY the JSON, no markdown fences or additional text."""


# --- Cross-Transcript Analysis ---

def cross_analysis_prompt(instructions: str) -> str:
    """Prompt for analyzing multiple transcripts together based on user instructions."""
    return f"""You are analyzing summaries from multiple video transcripts.

The user has provided the following instructions for this analysis:

{instructions}

Analyze the provided transcript summaries according to the user's instructions. Produce a structured report.

Return your response as valid JSON with this exact structure:
{{
  "report_title": "A concise title summarizing the analysis",
  "sections": [
    {{
      "heading": "Section heading",
      "content": "Detailed content for this section. Use plain text with line breaks for readability."
    }}
  ],
  "summary": "A brief overall summary of the analysis findings",
  "concept_map": {{
    "central_node": "The central theme or topic of this analysis",
    "branches": [
      {{
        "label": "A key theme or category",
        "importance": 0.8,
        "relationship_type": "supports",
        "children": [
          {{
            "label": "Specific finding",
            "importance": 0.6,
            "source_videos": ["Video Title"],
            "detail": "One-sentence elaboration of this finding"
          }}
        ]
      }}
    ]
  }}
}}

Guidelines:
- Create as many sections as needed to fully address the user's instructions
- Reference specific source videos by name when relevant
- Be thorough but concise
- The concept_map should capture the high-level structure of your analysis as a radial tree — the central_node is the core topic, each branch is a major theme, and children are specific findings under that theme
- Aim for 3-6 branches with 2-4 children each for a readable map
- For each branch, set importance (0.0-1.0) reflecting its significance to the central topic
- Set relationship_type to one of: "supports" (reinforces central theme), "contrasts" (challenges or opposes), or "extends" (adds new dimension)
- For each child, set importance (0.0-1.0), list source_videos by title, and include a brief detail sentence
- Return ONLY the JSON, no markdown fences or additional text."""


# --- Concept Map Regeneration ---

def regenerate_concept_map_prompt() -> str:
    """Prompt for regenerating just the concept map from an existing cross-analysis report."""
    return """You are given an existing cross-analysis report. Your task is to create a NEW concept map that captures the high-level structure of the analysis as a radial tree.

Return ONLY a valid JSON object with this exact structure — no markdown fences, no extra text:
{
  "central_node": "The central theme or topic of this analysis",
  "branches": [
    {
      "label": "A key theme or category",
      "importance": 0.8,
      "relationship_type": "supports",
      "children": [
        {
          "label": "Specific finding",
          "importance": 0.6,
          "source_videos": ["Video Title"],
          "detail": "One-sentence elaboration of this finding"
        }
      ]
    }
  ]
}

Guidelines:
- The central_node is the core topic tying the analysis together
- Aim for 3-6 branches with 2-4 children each for a readable map
- Set importance (0.0-1.0) reflecting significance to the central topic
- Set relationship_type to one of: "supports", "contrasts", or "extends"
- For each child, list source_videos by title and include a brief detail sentence
- Produce a FRESH perspective — reorganize themes differently than the report sections"""


# --- Legacy prompts (kept for backward compatibility with existing data) ---

def baseline_prompt(profile_name: str, profile_hints: str) -> str:
    """Legacy standalone baseline prompt. Use package_a_prompt for new analyses."""
    return f"""You are analyzing a {profile_name} transcript. {profile_hints}

Your task is to produce a structural analysis with three parts:

1. **OUTLINE**: Identify the major sections/segments of this content. For each section, provide:
   - A descriptive title
   - The approximate start timestamp (in seconds)
   - The approximate end timestamp (in seconds)
   - A one-sentence description of what's covered

2. **SUMMARY**: Write a concise overall summary (3-5 sentences) capturing the main topics, key takeaways, and notable points.

3. **TAGS**: Generate 3-5 short topic tags that describe the main subjects of this content. Tags should be lowercase, 1-2 words each, and capture the core topics (e.g., "machine learning", "python", "productivity", "startups").

Return your response as valid JSON with this exact structure:
{{
  "outline": [
    {{
      "title": "Section Title",
      "start_time": 0,
      "end_time": 120,
      "description": "Brief description of this section"
    }}
  ],
  "summary": "Overall summary text here.",
  "tags": ["tag1", "tag2", "tag3"]
}}

Return ONLY the JSON, no markdown fences or additional text."""
