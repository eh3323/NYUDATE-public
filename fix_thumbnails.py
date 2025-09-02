#!/usr/bin/env python3
"""
Script to generate missing thumbnails and fix 404 issues
"""

import os
import sys
from app import app, db, Evidence, generate_privacy_thumbnail, generate_document_placeholder

def fix_missing_thumbnails():
    """Generate thumbnails for evidence that don't have them"""
    with app.app_context():
        # Find evidence without thumbnails
        evidence_without_thumbnails = Evidence.query.filter(
            (Evidence.thumbnail_path == None) | (Evidence.thumbnail_path == '')
        ).all()
        
        print(f"Found {len(evidence_without_thumbnails)} evidence items without thumbnails")
        
        fixed_count = 0
        
        for evidence in evidence_without_thumbnails:
            print(f"Processing evidence {evidence.id} (category: {evidence.category})")
            
            try:
                thumbnail_path = None
                
                if evidence.category in ['image', 'chat_image'] and evidence.file_path:
                    if os.path.exists(evidence.file_path):
                        thumbnail_path = generate_privacy_thumbnail(evidence.file_path, evidence.id)
                    else:
                        print(f"  Original file not found: {evidence.file_path}")
                
                elif evidence.category in ['document', 'video', 'chat_video']:
                    thumbnail_path = generate_document_placeholder(
                        evidence.id, 
                        evidence.original_filename,
                        evidence.description
                    )
                
                if thumbnail_path:
                    evidence.thumbnail_path = thumbnail_path
                    db.session.add(evidence)
                    fixed_count += 1
                    print(f"  Generated thumbnail: {thumbnail_path}")
                else:
                    print(f"  Failed to generate thumbnail for evidence {evidence.id}")
                    
            except Exception as e:
                print(f"  Error processing evidence {evidence.id}: {e}")
        
        if fixed_count > 0:
            db.session.commit()
            print(f"\nFixed {fixed_count} thumbnails")
        else:
            print("\nNo thumbnails were generated")

def check_existing_thumbnails():
    """Check which thumbnails exist and which are missing"""
    with app.app_context():
        all_evidence = Evidence.query.all()
        print(f"Checking {len(all_evidence)} evidence items...")
        
        missing_files = []
        
        for evidence in all_evidence:
            if evidence.thumbnail_path:
                if not os.path.exists(evidence.thumbnail_path):
                    missing_files.append(evidence)
                    print(f"Missing thumbnail file for evidence {evidence.id}: {evidence.thumbnail_path}")
        
        print(f"\nFound {len(missing_files)} evidence items with missing thumbnail files")
        return missing_files

if __name__ == "__main__":
    print("Checking existing thumbnails...")
    missing = check_existing_thumbnails()
    
    print("\nGenerating missing thumbnails...")
    fix_missing_thumbnails()
    
    print("\nThumbnail fix completed!")