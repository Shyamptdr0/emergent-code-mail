# Auth-Gated App Testing Playbook (Emergent Google OAuth)

## Step 1: Create Test User & Session in MongoDB
```
mongosh --eval "
use('test_database');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({
  user_id: userId,
  email: 'test.user.' + Date.now() + '@example.com',
  name: 'Test User',
  picture: 'https://via.placeholder.com/150',
  ext_api_key: 'test_ext_key_' + Date.now(),
  created_at: new Date()
});
db.user_sessions.insertOne({
  user_id: userId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000),
  created_at: new Date()
});
print('Session token: ' + sessionToken);
print('User ID: ' + userId);
"
```

## Step 2: Test Backend
- `GET /api/auth/me` with `Authorization: Bearer <session_token>` → user profile
- Protected endpoints require cookie `session_token` OR Bearer token

## Step 3: Browser Cookie Set
```
await page.context.add_cookies([{
  "name": "session_token", "value": "<token>",
  "domain": "<your-domain>", "path": "/",
  "httpOnly": True, "secure": True, "sameSite": "None"
}])
```

Checklist: user has `user_id` (UUID), session `user_id` matches; all queries use `{"_id":0}`.
