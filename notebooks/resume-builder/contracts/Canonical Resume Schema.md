# Canonical Resume Schema
{
  "schema_version": "1.0",
  "header": {},
  "sections": []
}

## Purpose

The canonical resume is the system of record for all resume generation activities.

Goals:

* Separate content from presentation.
* Remain independent of rendering layout.
* Support multiple resume variants from the same source data.
* Preserve semantic structure rather than formatted text.

The canonical resume should contain all resume-relevant information but should not contain presentation concerns such as font sizes, spacing, bolding, page layout, or ordering rules.

---

# Top-Level Structure

```json
{
  "header": {},
  "sections": []
}
```

---

# Header

The header contains personal and contact information.

Example:

```json
{
  "header": {
    "name": "Douglas Gordon Daly",
    "title": "Principal AI Engineer / AI Solutions Architect",
    "location": "Portland, OR",
    "email": "douglasgdaly@gmail.com",
    "phone": "(650) 586-9720",
    "linkedin": "linkedin.com/in/douglasdaly",
    "github": "github.com/dougdaly"
  }
}
```

Additional fields may be added without changing the schema.

Examples:

* website
* clearance
* portfolio

---

# Sections

Every resume section follows the same structure.

```json
{
  "heading": "Summary",
  "type": "paragraph",
  "content": [...]
}
```

Fields:

| Field   | Description                 |
| ------- | --------------------------- |
| heading | Section title shown to user |
| type    | Content type                |
| content | Section contents            |

---

# Supported Section Types
The canonical schema intentionally contains a small number of content types.
New content types should only be introduced when an existing type cannot accurately represent the information.
## paragraph

Content is a list of paragraphs.

```json
{
  "heading": "Summary",
  "type": "paragraph",
  "content": [
    "Principal AI Engineer..."
  ]
}
```

---

## bullet

Content is a list of bullet strings.

```json
{
  "heading": "Highlights",
  "type": "bullet",
  "content": [
    "...",
    "..."
  ]
}
```

---

## inline_list

Content is a list of short phrases.
Renderers may display inline lists using commas, pipes, bullets, or other compact layouts.

```json
{
  "type": "inline_list",
  "content": [
    "Python",
    "SQL",
    "BigQuery"
  ]
}
```

---

## subsections

Use `subsections` when a section or content block contains a list of named child records.

A subsection is appropriate when each child entry has a meaningful label and may optionally include context, dates, and supporting content.

Good uses:
- Core Technologies categories
- Core Expertise categories
- Education entries
- Patents
- Awards
- Certifications
- Client work under a consulting role

Avoid using `subsections` just to add arbitrary formatting inside a paragraph. If the content is only prose, use `paragraph`. If the content is only bullets, use `bullet`.

Example:
```json
{
  "heading": "Education",
  "type": "subsections",
  "content":
  [
    {
      "label": "MBA",
      "context": "UCLA Anderson School of Management",
      "type": "inline_list",
      "content": ["Top Honors", "GPA: 3.9"]
    },
    {
      "label": "M.S., Applied Statistics",
      "context": "Rochester Institute of Technology",
      "type": "inline_list",
      "content": ["GPA: 3.9"]
    }
  ]
}
```

---

## experience

Content contains structured experience entries.

```json
{
  "heading": "Selected Experience",
  "type": "experience",
  "content": [...]
}
```

---

# Experience Object

```json
{
  "role": "Head of Data Science",
  "organization": "Facteus",
  "dates": "Oct 2017 - Nov 2020",
  "role_context": "Led data science and data-product initiatives on Facteus' 30B+ transaction dataset, the company’s core source for market-intelligence products and revenue-generating analytics.",
  "type": "bullet",
  "content": [
    "Developed merchant, brand, industry, and storefront resolution methodologies..."
  ]
}
```

Fields:

| Field        | Required | Description        |
|--------------|----------|--------------------|
| role         | Yes      | Position title     |
| organization | Yes      | Employer           |
| dates        | No       | Date range         |
| role_context | No       | Optional explanation of role scope, business context, scale, operating environment, or why the work mattered. Extracted from CONTEXT: lines when present.|
| type         | No       | Content type       |
| content      | No       | Supporting content |

---

# Subsection Object

A subsection is a reusable labeled child record.

```json
{
  "label": "AI & Machine Learning",
  "type": "inline_list",
  "content": [
    "LLMs",
    "RAG",
    "Agentic AI"
  ]
}
```
Or:

```json
{
  "label": "Consolidated Edison",
  "context": "via ABC Consulting",
  "dates": "Jan 2026 - Present",
  "type": "bullet",
  "content": [...]
}
```

Fields:

| Field   | Required | Description                                                                              |
| ------- | -------: | ---------------------------------------------------------------------------------------- |
| label   |      Yes | Primary label for the child record                                                       |
| context |       No | Secondary context such as institution, issuer, client relationship, source or description|
| dates   |       No | Date or date range                                                                       |
| type    |       No | Content type for supporting details                                                      |
| content |       No | Supporting content interpreted according to `type`                                       |


---

# Renderer Responsibility

Renderers consume the canonical resume.

Renderers control:

* Fonts
* Spacing
* Page layout
* Bold / italic styling
* Header arrangement
* PDF / DOCX generation

Renderers must not modify resume content.
Renderers may display subsections in different layouts, including:

- stacked
- labeled inline
- compact inline
- heading plus bullets

The JSON should not encode the visual layout.

---

# Layout Responsibility

YAML layout files define presentation rules.

Examples:

* standard.yaml
* compact.yaml
* executive.yaml
* anonymous.yaml

Layout files may change appearance but must not change resume content.

