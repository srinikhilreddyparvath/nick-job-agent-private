import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

from app.models.application_package import TailoredResumeData


def safe_filename(value:str)->str:
    return re.sub(r"[^A-Za-z0-9]+","-",value).strip("-")[:80] or "Role"


class ResumeRenderer:
    def __init__(self,root:Path|None=None):
        self.root=root or Path(__file__).resolve().parents[3]/"generated"/"applications"
    def render(self,job_id:int,resume:TailoredResumeData)->Path:
        folder=self.root/str(job_id);folder.mkdir(parents=True,exist_ok=True)
        filename=f"{safe_filename(resume.professional_name)}-{safe_filename(resume.target_company)}-{safe_filename(resume.target_role)}-Resume.pdf";path=folder/filename
        styles=getSampleStyleSheet();styles.add(ParagraphStyle(name="Name",parent=styles["Title"],fontName="Helvetica-Bold",fontSize=18,leading=21,alignment=TA_CENTER,spaceAfter=4));styles.add(ParagraphStyle(name="Contact",parent=styles["Normal"],fontSize=8.5,leading=11,alignment=TA_CENTER,textColor=colors.HexColor("#263447")));styles.add(ParagraphStyle(name="Section",parent=styles["Heading2"],fontName="Helvetica-Bold",fontSize=10,leading=12,spaceBefore=8,spaceAfter=4,textColor=colors.HexColor("#12243a"),borderWidth=0,borderPadding=0));styles.add(ParagraphStyle(name="BodySmall",parent=styles["BodyText"],fontSize=8.7,leading=11.2,spaceAfter=2));styles.add(ParagraphStyle(name="Role",parent=styles["BodyText"],fontName="Helvetica-Bold",fontSize=9.2,leading=11,spaceBefore=4,spaceAfter=2))
        doc=SimpleDocTemplate(str(path),pagesize=letter,rightMargin=.62*inch,leftMargin=.62*inch,topMargin=.48*inch,bottomMargin=.48*inch,title=f"{resume.professional_name} - {resume.target_role}",author=resume.professional_name)
        story=[Paragraph(resume.professional_name,styles["Name"])]
        contact=[resume.email,resume.phone,resume.location or "",resume.portfolio_url or "",resume.linkedin_url or ""];story+=[Paragraph(" | ".join(x for x in contact if x),styles["Contact"]),Paragraph(f"Target: {resume.target_role} at {resume.target_company}",styles["Contact"]),Spacer(1,5)]
        story+=[Paragraph("PROFESSIONAL SUMMARY",styles["Section"]),Paragraph(" ".join(x.text for x in resume.summary),styles["BodySmall"])]
        story+=[Paragraph("EXPERIENCE",styles["Section"])]
        grouped:dict[str,list]= {}
        for bullet in resume.bullets:grouped.setdefault(bullet.employer_or_context,[]).append(bullet)
        for context,bullets in grouped.items():
            parts=context.split(" | ",1);role_line=f"{parts[0]}"+(f" - {parts[1]}" if len(parts)>1 else "")
            items=[ListItem(Paragraph((x.edited_text or x.generated_text),styles["BodySmall"]),leftIndent=10) for x in bullets]
            story.append(KeepTogether([Paragraph(role_line,styles["Role"]),ListFlowable(items,bulletType="bullet",start="circle",leftIndent=14,bulletFontSize=5)]))
        story+=[Paragraph("SKILLS",styles["Section"]),Paragraph(" | ".join(x.text for x in resume.skills),styles["BodySmall"]),Paragraph("EDUCATION",styles["Section"])]
        for item in resume.education:story.append(Paragraph(item.text,styles["BodySmall"]))
        doc.build(story);return path
