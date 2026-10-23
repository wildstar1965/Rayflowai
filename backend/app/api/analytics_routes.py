import sqlite3
from fastapi import APIRouter, HTTPException
from app.services.job_history import analytics

router = APIRouter(prefix='/api', tags=['analytics'])


@router.get('/analytics')
def get_analytics():
    try:
        return analytics()
    except (OSError, sqlite3.Error):
        raise HTTPException(503, 'Job history is unavailable. Check persistent storage permissions.') from None
