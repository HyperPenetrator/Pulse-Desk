import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from config import settings

# Initialize Firebase Admin SDK if not in mock mode
firebase_app = None
if not settings.USE_MOCK_AUTH:
    import firebase_admin
    from firebase_admin import credentials
    if not firebase_admin._apps:
        firebase_admin.initialize_app()

security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    token = credentials.credentials
    if settings.USE_MOCK_AUTH:
        try:
            decoded = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )
            return decoded
        except jwt.PyJWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid or expired mock token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )
    else:
        try:
            from firebase_admin import auth as firebase_auth
            decoded = firebase_auth.verify_id_token(token)
            return decoded
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid or expired Firebase ID token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )
