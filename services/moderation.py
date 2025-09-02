"""
Content moderation service for NYU CLASS Professor Review System

This module contains functions for content moderation using OpenAI API.
"""

import os
import json
import openai
from flask import current_app


class ModerationService:
    """Service for content moderation using OpenAI API"""
    
    @staticmethod
    def _get_openai_client():
        """Initialize and return OpenAI client"""
        api_key = current_app.config.get('OPENAI_API_KEY')
        if not api_key:
            return None
            
        if current_app.config.get('OPENAI_BASE_URL'):
            return openai.OpenAI(api_key=api_key, base_url=current_app.config.get('OPENAI_BASE_URL'))
        else:
            return openai.OpenAI(api_key=api_key)
    
    @staticmethod
    def _parse_version(version_str: str) -> tuple:
        """Parse version string to tuple"""
        parts = version_str.split(".")
        try:
            return tuple(int(x) for x in parts[:3])
        except Exception:
            return (0, 0, 0)
    
    @staticmethod
    def _check_sdk_version() -> bool:
        """Check if OpenAI SDK version supports Responses API"""
        ver = str(getattr(openai, "__version__", "0.0.0")).split("+")[0]
        return ModerationService._parse_version(ver) >= (1, 55, 0)
    
    @staticmethod
    def _load_config_files(prompt_filename: str, schema_filename: str) -> tuple:
        """Load prompt and schema configuration files"""
        # Files are in the root directory of the app
        prompt_path = os.path.join(current_app.root_path, prompt_filename)
        schema_path = os.path.join(current_app.root_path, schema_filename)
        
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_content = f.read()
        
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_content = json.loads(f.read())
            
        return prompt_content, schema_content
    
    @staticmethod
    def _create_default_response(action='ALLOW', reasons=None, client_notice=''):
        """Create default moderation response"""
        return {
            'action': action,
            'reasons': reasons or [],
            'client_notice': client_notice
        }
    
    @staticmethod
    def _validate_response(result: dict) -> dict:
        """Validate and normalize moderation response"""
        # 确保client_notice字段存在且为有效字符串
        if 'client_notice' not in result:
            result['client_notice'] = ''
        elif result['client_notice'] is None:
            result['client_notice'] = ''
        elif not isinstance(result['client_notice'], str):
            result['client_notice'] = str(result['client_notice'])
        
        # 如果是FLAG_AND_FIX但client_notice为空，提供默认消息
        if result.get('action') == 'FLAG_AND_FIX' and not result['client_notice'].strip():
            result['client_notice'] = '内容需要修改，请修改后重新提交'
        
        return result
    
    @staticmethod
    def moderate_content(text: str) -> dict:
        """
        使用OpenAI API对文本内容进行审核
        返回审核结果字典
        """
        try:
            # 检查是否启用内容审核
            if not current_app.config.get('CONTENT_MODERATION_ENABLED', True):
                return ModerationService._create_default_response(reasons=['Content moderation disabled'])
            
            # 获取OpenAI客户端
            client = ModerationService._get_openai_client()
            if not client:
                current_app.logger.warning("OpenAI API key not configured, skipping content moderation")
                return ModerationService._create_default_response(reasons=['API key not configured'])
            
            # 检查SDK版本
            if not ModerationService._check_sdk_version():
                current_app.logger.error("OpenAI SDK too old for Responses API (need >= 1.55)")
                return ModerationService._create_default_response(reasons=['OpenAI SDK too old (need >= 1.55)'])
            
            # 读取配置文件
            try:
                prompt_content, schema_content = ModerationService._load_config_files('Prompt.txt', 'json.txt')
            except Exception as e:
                current_app.logger.error(f"Failed to read prompt or schema files: {e}")
                return ModerationService._create_default_response(reasons=['Config file error'])
            
            # 调用OpenAI API
            current_app.logger.info("Calling OpenAI Responses API for content moderation... model=%s, timeout=%ss", 
                                   current_app.config.get('OPENAI_MODEL', 'gpt-5'), 
                                   current_app.config.get('OPENAI_API_TIMEOUT', 30))
            
            response = client.responses.create(
                model=current_app.config.get('OPENAI_MODEL', 'gpt-5'),
                input=f"{prompt_content}\n\n用户内容：\n{text}",
                reasoning={'effort': 'minimal'},
                text={
                    'verbosity': 'low',
                    'format': {
                        'type': 'json_schema',
                        'name': schema_content.get('name', 'ModerationSchema'),
                        'schema': schema_content.get('schema', {}),
                        'strict': bool(schema_content.get('strict', False)),
                    },
                },
                timeout=current_app.config.get('OPENAI_API_TIMEOUT', 30),
            )
            
            current_app.logger.info("OpenAI response received. id=%s", getattr(response, 'id', '<no id>'))
            
            # 解析响应
            result = None
            try:
                output_text = getattr(response, 'output_text', None)
                if output_text:
                    result = json.loads(output_text)
            except Exception:
                result = None
                
            if result is None:
                try:
                    output = getattr(response, 'output', None)
                    if output:
                        for item in output:
                            contents = getattr(item, 'content', [])
                            for content in contents:
                                content_json = getattr(content, 'json', None)
                                if content_json is not None:
                                    result = content_json
                                    break
                            if result is not None:
                                break
                except Exception:
                    result = None
            
            if result is None:
                raise json.JSONDecodeError("No JSON output found", doc=str(response), pos=0)
            
            # 记录审核日志
            current_app.logger.info(f"Content moderation result: {result.get('action', 'UNKNOWN')}")
            
            return ModerationService._validate_response(result)
            
        except openai.APITimeoutError:
            current_app.logger.error("OpenAI API timeout")
            return ModerationService._create_default_response(reasons=['API timeout'])
        except openai.APIError as e:
            current_app.logger.error(f"OpenAI API error: {e}")
            return ModerationService._create_default_response(reasons=['API error'])
        except json.JSONDecodeError as e:
            current_app.logger.error(f"Failed to parse OpenAI response: {e}")
            return ModerationService._create_default_response(reasons=['Response parse error'])
        except Exception as e:
            current_app.logger.error(f"Unexpected error in content moderation: {e}")
            return ModerationService._create_default_response(reasons=['System error'])
    
    @staticmethod
    def moderate_comment(content: str) -> dict:
        """
        使用OpenAI API对评论内容进行审核
        返回审核结果字典
        """
        try:
            # 检查是否启用内容审核
            if not current_app.config.get('CONTENT_MODERATION_ENABLED', True):
                return ModerationService._create_default_response(reasons=['Content moderation disabled'])
            
            # 获取OpenAI客户端
            client = ModerationService._get_openai_client()
            if not client:
                current_app.logger.warning("OpenAI API key not configured, skipping comment moderation")
                return ModerationService._create_default_response(reasons=['API key not configured'])
            
            # 检查SDK版本
            if not ModerationService._check_sdk_version():
                current_app.logger.error("OpenAI SDK too old for Responses API (need >= 1.55)")
                return ModerationService._create_default_response(reasons=['OpenAI SDK too old (need >= 1.55)'])
            
            # 读取评论审核的配置文件
            try:
                prompt_content, schema_content = ModerationService._load_config_files('Comment Prompt.txt', 'comment schema.json')
            except Exception as e:
                current_app.logger.error(f"Failed to read comment prompt or schema files: {e}")
                return ModerationService._create_default_response(reasons=['Config file error'])
            
            # 调用OpenAI API
            current_app.logger.info("Calling OpenAI Responses API for comment moderation... model=%s", 
                                   current_app.config.get('OPENAI_MODEL', 'gpt-5'))
            
            response = client.responses.create(
                model=current_app.config.get('OPENAI_MODEL', 'gpt-5'),
                input=f"{prompt_content}\n\n用户内容：\n{content}",
                reasoning={'effort': 'minimal'},
                text={
                    'verbosity': 'low',
                    'format': {
                        'type': 'json_schema',
                        'name': schema_content.get('name', 'CommentPIIModeration'),
                        'schema': schema_content.get('schema', {}),
                        'strict': bool(schema_content.get('strict', False)),
                    },
                },
                timeout=current_app.config.get('OPENAI_API_TIMEOUT', 30),
            )
            
            # 解析响应
            result = None
            try:
                output_text = getattr(response, 'output_text', None)
                if output_text:
                    result = json.loads(output_text)
            except Exception:
                result = None
                
            if result is None:
                try:
                    output = getattr(response, 'output', None)
                    if output:
                        for item in output:
                            contents = getattr(item, 'content', [])
                            for content_item in contents:
                                content_json = getattr(content_item, 'json', None)
                                if content_json is not None:
                                    result = content_json
                                    break
                            if result is not None:
                                break
                except Exception:
                    result = None
            
            if result is None:
                raise json.JSONDecodeError("No JSON output found", doc=str(response), pos=0)
            
            # 记录审核日志
            current_app.logger.info(f"Comment moderation result: {result.get('action', 'UNKNOWN')}")
            
            return ModerationService._validate_response(result)
            
        except openai.APITimeoutError:
            current_app.logger.error("OpenAI API timeout for comment")
            return ModerationService._create_default_response(reasons=['API timeout'])
        except openai.APIError as e:
            current_app.logger.error(f"OpenAI API error for comment: {e}")
            return ModerationService._create_default_response(reasons=['API error'])
        except json.JSONDecodeError as e:
            current_app.logger.error(f"Failed to parse OpenAI response for comment: {e}")
            return ModerationService._create_default_response(reasons=['Response parse error'])
        except Exception as e:
            current_app.logger.error(f"Unexpected error in comment moderation: {e}")
            return ModerationService._create_default_response(reasons=['Unexpected error'])


# Convenience functions for backward compatibility
def moderate_content(text: str) -> dict:
    """Convenience function for content moderation"""
    return ModerationService.moderate_content(text)


def moderate_comment(content: str) -> dict:
    """Convenience function for comment moderation"""
    return ModerationService.moderate_comment(content)