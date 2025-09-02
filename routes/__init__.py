"""
Routes package for NYU CLASS Professor Review System

This package contains all route blueprints and initialization functions.
"""

def init_all_routes(app, database_instance, models, moderate_content_func, verify_turnstile_func=None, generate_thumbnails_async_func=None, send_email_async_func=None, generate_document_placeholder_func=None):
    """Initialize all route blueprints"""
    
    # Import blueprint initialization functions
    from .admin import init_admin_routes
    from .api import init_api_routes
    from .main import init_main_routes
    from .submission import init_submission_routes
    from .evidence import init_evidence_routes
    from .appeal import init_appeal_routes
    from .dev import init_dev_routes
    
    functions = {
        'moderate_content': moderate_content_func,
        'verify_turnstile': verify_turnstile_func,
        'generate_thumbnails_async': generate_thumbnails_async_func,
        'send_email_async': send_email_async_func,
        'generate_document_placeholder': generate_document_placeholder_func
    }
    
    # Initialize blueprints
    admin_blueprint = init_admin_routes(database_instance, models)
    api_blueprint = init_api_routes(database_instance, models, moderate_content_func)
    main_blueprint = init_main_routes(database_instance, models)
    submission_blueprint = init_submission_routes(database_instance, models, functions)
    evidence_blueprint = init_evidence_routes(database_instance, models, functions)
    appeal_blueprint = init_appeal_routes(database_instance, models, functions)
    dev_blueprint = init_dev_routes(database_instance, models)
    
    # Register blueprints
    app.register_blueprint(admin_blueprint)
    app.register_blueprint(api_blueprint)
    app.register_blueprint(main_blueprint)
    app.register_blueprint(submission_blueprint)
    app.register_blueprint(evidence_blueprint)
    app.register_blueprint(appeal_blueprint)
    app.register_blueprint(dev_blueprint)
    
    return {
        'admin': admin_blueprint,
        'api': api_blueprint,
        'main': main_blueprint,
        'submission': submission_blueprint,
        'evidence': evidence_blueprint,
        'appeal': appeal_blueprint,
        'dev': dev_blueprint
    }