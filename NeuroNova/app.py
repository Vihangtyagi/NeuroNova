"""
Neuronova — AI-Based Cognitive Gaming & Memory Assistance Platform
for Elderly Dementia Patients in the North Eastern Region (SIH26003)

This is just the entry point: it wires up the database and hands off to
frontend.py, which owns every screen, layout and style the user sees.

Run with:  streamlit run app.py
"""

import db
import frontend

db.init_db()
frontend.run()
