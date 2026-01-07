from fastapi import FastAPI, APIRouter, Request, Response, Body
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel
from typing import Dict, Any
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import inch
from io import BytesIO
import json
from datetime import datetime

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app
app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory=str(ROOT_DIR / "static")), name="static")

# Templates
templates = Jinja2Templates(directory=str(ROOT_DIR / "templates"))

# Create API router
api_router = APIRouter(prefix="/api")

# Models
class PDFContentModel(BaseModel):
    title: str
    content: str
    type: str

# HTML Routes (serving templates)
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/functions", response_class=HTMLResponse)
async def functions(request: Request):
    return templates.TemplateResponse("functions.html", {"request": request})

# API Routes
@api_router.get("/")
async def root():
    return {"message": "GTIE Services API"}

@api_router.post("/generate-pdf")
async def generate_pdf(data: PDFContentModel):
    """Generate PDF from content"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a1a2e'),
        spaceAfter=30,
    )
    story.append(Paragraph(data.title, title_style))
    story.append(Spacer(1, 12))
    
    # Content based on type
    if data.type == 'docs':
        # Simple text document
        content_style = styles['Normal']
        for line in data.content.split('\n'):
            if line.strip():
                story.append(Paragraph(line, content_style))
                story.append(Spacer(1, 12))
    
    elif data.type == 'agenda':
        # Parse agenda items
        try:
            items = json.loads(data.content)
            table_data = [['Título', 'Data', 'Hora', 'Status']]
            for item in items:
                table_data.append([
                    item.get('title', ''),
                    item.get('date', ''),
                    item.get('time', ''),
                    'Concluído' if item.get('completed') else 'Pendente'
                ])
            
            table = Table(table_data, colWidths=[2.5*inch, 1.5*inch, 1*inch, 1.5*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f3460')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 14),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(table)
        except:
            story.append(Paragraph(data.content, styles['Normal']))
    
    elif data.type == 'planilhas':
        # Parse spreadsheet data
        try:
            rows = json.loads(data.content)
            if rows:
                table = Table(rows)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16213e')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 12),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                story.append(table)
        except:
            story.append(Paragraph(data.content, styles['Normal']))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    
    # Return PDF
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={data.title.replace(' ', '_')}.pdf"}
    )

# Include API router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()