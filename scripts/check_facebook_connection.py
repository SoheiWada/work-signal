#!/usr/bin/env python3
"""Read-only Page connection check. Never prints credentials or raw API errors."""
import json
import os
import sys
try:
    from . import publish_social as social
except ImportError:
    import publish_social as social


def main():
    try:
        token = os.environ.get('FACEBOOK_PAGE_ACCESS_TOKEN')
        if not token:
            raise RuntimeError('Page secret missing')
        social.facebook.policy(social.ROOT)
        profile = social.facebook.verify_account(social.request_json, token)
        items = social.facebook.history(social.request_json, token)
        print(json.dumps({'page_id':profile['id'], 'verified_identity':True,
                          'complete_history':True, 'posts_read':len(items),
                          'publish_permission_verified':False, 'posts_created':0}))
        return 0
    except Exception as exc:
        print(json.dumps({'verified_identity':False, 'error_type':type(exc).__name__,
                          'posts_created':0}),file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
