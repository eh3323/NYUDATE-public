"""
Models package for NYU CLASS Professor Review System

This package contains all database models and related utilities.
"""

# Store initialized models to prevent re-initialization
_initialized_models = None

def init_models(database_instance):
    """Initialize models with the database instance from the main app"""
    global _initialized_models
    
    # Return cached models if already initialized
    if _initialized_models is not None:
        return _initialized_models
    
    # Import model factory functions
    from .submission import create_submission_model, ReviewStatus, mask_name
    from .evidence import create_evidence_model
    from .appeal import create_appeal_models
    from .interaction import create_interaction_models
    
    # Create model classes
    Submission = create_submission_model(database_instance)
    Evidence = create_evidence_model(database_instance)
    Appeal, AppealEvidence = create_appeal_models(database_instance)
    Like, Comment = create_interaction_models(database_instance)
    
    # Cache and return all model classes and utilities
    _initialized_models = {
        'ReviewStatus': ReviewStatus,
        'Submission': Submission,
        'Evidence': Evidence,
        'Appeal': Appeal,
        'AppealEvidence': AppealEvidence,
        'Like': Like,
        'Comment': Comment,
        'mask_name': mask_name
    }
    
    return _initialized_models

# Convenience imports (will be available after init_models is called)
__all__ = [
    'init_models',
    'ReviewStatus',
    'Submission', 
    'Evidence',
    'Appeal',
    'AppealEvidence',
    'Like',
    'Comment',
    'mask_name'
]