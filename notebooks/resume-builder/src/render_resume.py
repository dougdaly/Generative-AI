from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
import json
from pathlib import Path

def set_margins(section, top=0.45, bottom=0.45, left=0.55, right=0.55):
    section.top_margin = Inches(top)
    section.bottom_margin = Inches(bottom)
    section.left_margin = Inches(left)
    section.right_margin = Inches(right)

def set_font(run, size=9, bold=False):
    run.font.name = "Arial"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")
    run.font.size = Pt(size)
    run.bold = bold

def add_section_heading(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(text.upper())
    set_font(r, size=9, bold=True)

def add_bullet(doc, text):
    p = doc.add_paragraph(style=None)
    p.paragraph_format.left_indent = Inches(0.16)
    p.paragraph_format.first_line_indent = Inches(-0.16)
    p.paragraph_format.space_after = Pt(1.5)
    r = p.add_run("• " + text)
    set_font(r, size=8.5)

def add_role(doc, heading, subheading, bullets):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(1)
    r = p.add_run(heading)
    set_font(r, size=9, bold=True)
    r = p.add_run(" | " + subheading)
    set_font(r, size=8.5)

    for b in bullets:
        add_bullet(doc, b)

def render_resume(resume, out_path):
    doc = Document()
    set_margins(doc.sections[0])

    styles = doc.styles
    styles["Normal"].font.name = "Arial"
    styles["Normal"].font.size = Pt(8.5)

    # Header
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Douglas Gordon Daly")
    set_font(r, size=14, bold=True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Portland, OR | douglasgdaly@gmail.com | (650) 586-9720 | linkedin.com/in/douglasdaly | github.com/dougdaly")
    set_font(r, size=8)

    # Target title
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(resume["target_title"])
    set_font(r, size=10, bold=True)

    # Summary
    add_section_heading(doc, "Summary")
    for item in resume["summary"]:
        add_bullet(doc, item)

    # Expertise / technologies
    add_section_heading(doc, "Core Expertise")
    p = doc.add_paragraph()
    r = p.add_run(" | ".join(resume["core_expertise"]))
    set_font(r, size=8.5)

    add_section_heading(doc, "Technologies")
    p = doc.add_paragraph()
    r = p.add_run(" | ".join(resume["technologies"]))
    set_font(r, size=8.2)

    # Selected experience
    add_section_heading(doc, "Selected Experience")
    for role in resume["selected_experience"]:
        add_role(
            doc,
            role["heading"],
            role["subheading"],
            role.get("bullets", [])
        )

    # Additional experience
    add_section_heading(doc, "Additional Experience")
    for role in resume["additional_experience"]:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(1)
        r = p.add_run(f'{role["heading"]} | {role["subheading"]}')
        set_font(r, size=8.5)

    # Selected projects
    add_section_heading(doc, "Selected Projects")
    for project in resume["selected_projects"]:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(1)
        r = p.add_run(project["heading"])
        set_font(r, size=8.5, bold=True)
        for b in project.get("bullets", []):
            add_bullet(doc, b)

    # Education
    add_section_heading(doc, "Education")
    p = doc.add_paragraph()
    r = p.add_run(" | ".join(resume["education"]))
    set_font(r, size=8.2)

    # Honors
    add_section_heading(doc, "Honors & Awards")
    for item in resume["honors_awards"]:
        add_bullet(doc, item)

    doc.save(out_path)

with open("artifacts/target_resume_v1.json") as f:
    target_resume_v1 = json.load(f)

render_resume(
    target_resume_v1,
    "artifacts/douglas_daly_principal_ai_engineer_v1.docx"
)