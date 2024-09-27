import random
from django.shortcuts import render
from django.utils import timezone
from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile
from django.core.mail import EmailMultiAlternatives
from django.utils.decorators import method_decorator
from django.contrib.auth import logout, authenticate, login
from django.views.decorators.csrf import csrf_exempt
from rest_framework import viewsets, status, generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import CustomUserSerializer, ContactMessageSerializer, \
    UserProfileUpdateSerializer, ScoresSerializer, ScoreRecordSerializer, SubscriptionCreateSerializer, \
    SubscriptionDetailSerializer
from .models import CustomUser, Contact, Scores, Emotion, ScoreRecord, Subscription
from django.conf import settings

import logging

logger = logging.getLogger(__name__)
CustomUser = get_user_model()


@method_decorator(csrf_exempt, name='dispatch')
class UserSignupViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.all()
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        try:
            name = request.data.get('name')
            email = request.data.get('email')
            password = request.data.get('password')

            if not email or not password:
                return Response(
                    {"message": "Both email and password are required.", "data": {}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if CustomUser.objects.filter(email=email).exists():
                return Response(
                    {"message": "User with this email already exists.", "data": {}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = CustomUser.objects.create_user(name=name, email=email, password=password)
            user.save()

            return Response(
                {"message": "User created successfully.",
                 "data": {"id": user.id, "name": user.name, "email": user.email}},
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response(
                {"message": f"Error: {str(e)}", "data": {}},
                status=status.HTTP_400_BAD_REQUEST
            )

    def destroy(self, request, *args, **kwargs):
        try:
            print(kwargs.get('pk'))  # Log the primary key
            user = get_object_or_404(CustomUser, pk=kwargs.get('pk'))
            user.delete()
            return Response({"message": "User deleted successfully"}, status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response(
                {"message": f"Error: {str(e)}", "data": {}},
                status=status.HTTP_400_BAD_REQUEST
            )


class SubscriptionListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        try:
            subscription_plans = [
                {"id": "1", "name": "Free", "description": "Free", "amount": 0,
                 "duration": "14 Days", "expiry_date": "null"},
                {"id": "2", "name": "Monthly", "description": "Full Customisation and Tracking.", "amount": 4.00,
                 "duration": "1 month", "expiry_date": "null"},
                {"id": "3", "name": "Yearly", "description": "Full Customisation and Tracking.", "amount": 29.99,
                 "duration": "12 months", "expiry_date": "null"},
            ]
            return Response(
                {
                    "message": "Subscription plans retrieved successfully.",
                    "data": subscription_plans,
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {
                    "message": f"Error: {str(e)}",
                    "data": {},
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SubscriptionCreateView(generics.CreateAPIView):
    serializer_class = SubscriptionCreateSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            subscription = self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)

            # Determine if the trial is valid
            is_trial_valid = None
            if subscription.subscription == 'free':
                if subscription.is_active and subscription.expiry_date >= timezone.now().date():
                    is_trial_valid = True

            subscription_data = SubscriptionCreateSerializer(subscription).data
            response_data = {
                "subscription": subscription_data,
                "isTrialValid": is_trial_valid
            }

            return self._response(
                {"message": "Subscription created successfully.", "data": response_data},
                status.HTTP_201_CREATED,
                headers
            )
        except ValidationError:
            return self._response(
                {"message": "Not a valid subscription", "data": serializer.errors},
                status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return self._response(
                {"message": "An unexpected error occurred", "data": str(e)},
                status.HTTP_400_BAD_REQUEST
            )

    def perform_create(self, serializer):
        return serializer.save(user=self.request.user)

    def _response(self, message_data, status_code, headers=None):
        return Response(message_data, status=status_code, headers=headers)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email", None)
        password = request.data.get("password", None)

        if not email or not password:
            return Response(
                {"message": "Both email and password are required.", "data": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, email=email, password=password)

        if user:
            login(request, user)
            refresh = RefreshToken.for_user(user)
            subscription = Subscription.objects.filter(user=user).order_by('-created_at').first()
            subscription_data = SubscriptionDetailSerializer(subscription).data if subscription else None

            # Check isTrialValid logic
            is_trial_valid = None
            if subscription:
                if subscription.subscription == "free":
                    if subscription.is_active and subscription.expiry_date >= timezone.now().date():
                        is_trial_valid = True
                    else:
                        is_trial_valid = False

            data = {
                "refresh_token": str(refresh),
                "access_token": str(refresh.access_token),
                "email": email,
                "name": user.name,
                "user_id": user.id,
                "image": request.build_absolute_uri(user.image.url) if user.image else None,
                "subscription": subscription_data,
                "isTrialValid": is_trial_valid,
            }
            return Response(
                {"message": "Logged in successfully.", "data": data},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"message": "Invalid Credentials. Try Again.", "data": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )


class UserLogoutViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def logout(self, request):
        refresh_token = request.data.get("refresh_token", None)

        if not refresh_token:
            return Response(
                {"message": "Refresh token is required.", "data": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            logout(request)
            return Response(
                {"message": "User logged out successfully.", "data": {}},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"message": "Invalid token or token has already been blacklisted.", "data": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )


class PasswordResetView(APIView):
    def post(self, request):
        email = request.data.get('email')

        user = CustomUser.objects.filter(email=email).first()
        if not user:
            return Response(
                {'message': 'User with this email does not exist.', "data": {}},
                status=status.HTTP_404_NOT_FOUND
            )

        # Generate a unique UID
        while True:
            code = random.randint(1000000, 9999999)
            if not CustomUser.objects.filter(uid=code).exists():
                break

        user.uid = code
        user.save()

        reset_url = f"https://emdradmin.pythonanywhere.com/mindmend/reset-password/form/{code}/"

        text_content = f"Please click the following link to reset your password: {reset_url}"
        html_content = f"""
        <html>
            <body>
                <p>This is an important message.</p>
                <p>Please click the following link to reset your password:</p>
                <a href="{reset_url}">{reset_url}</a>
            </body>
        </html>
        """

        msg = EmailMultiAlternatives(
            "Password Reset Link", text_content, settings.EMAIL_HOST_USER, [user.email]
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send()

        return Response(
            {'message': 'Password reset link has been sent to your email.'},
            status=status.HTTP_200_OK
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        uid = request.data.get('UID')
        new_password = request.data.get('new_password')

        if not uid or not new_password:
            return Response(
                {"message": "UID and new password are required.", "data": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = CustomUser.objects.filter(uid=uid).first()
        if not user:
            return Response(
                {'message': 'Invalid UID.', "data": {}},
                status=status.HTTP_404_NOT_FOUND
            )

        user.set_password(new_password)
        user.uid = None
        user.save()
        return Response(
            {"message": "Password has been reset successfully.", "data": {"user_id": user.id}},
            status=status.HTTP_200_OK
        )


def password_reset_form(request, uid):
    return render(request, 'forget_password.html', {'uid': uid})


class ContactUsAPIView(APIView):
    def post(self, request, format=None):
        serializer = ContactMessageSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            if Contact.objects.filter(email=email).exists():
                return Response(
                    {'message': 'Email already exists in database.', "data": {}},
                    status=status.HTTP_409_CONFLICT
                )

            contact_instance = serializer.save()
            data = {
                'email': email,
                'message': serializer.validated_data['message'],
                'contact_id': contact_instance.id,
            }

            return Response(
                {'message': 'Message sent successfully.', 'data': data},
                status=status.HTTP_201_CREATED
            )

        return Response(
            {'message': 'Failed to send message.', 'data': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class UserListAPIView(APIView):
    def get(self, request, format=None):
        users = CustomUser.objects.all()

        if not users.exists():
            return Response(
                {"message": "No users in the database."},
                status=status.HTTP_200_OK
            )

        serializer = CustomUserSerializer(users, many=True)
        names = users.values_list('name', flat=True)

        return Response(
            {
                "message": "Users retrieved successfully.",
                "data": serializer.data,
                "names": list(names)
            },
            status=status.HTTP_200_OK
        )


class UserTherapyInfoAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_data = request.data.copy()
        request_data['user'] = request.user.id

        scores = Scores.objects.filter(user=request.user).first()
        if scores:
            serializer = ScoresSerializer(scores, data=request_data, partial=True)
        else:
            serializer = ScoresSerializer(data=request_data)

        if serializer.is_valid():
            scores = serializer.save(user=request.user)
            if 'selected_emotions' in request_data:
                scores.selected_emotions.set(request_data['selected_emotions'])
                # Ensure the score record reflects the latest emotions
                scores.create_score_record()
            return Response(
                {"message": "User therapy info created successfully.", "data": serializer.data},
                status=status.HTTP_201_CREATED
            )
        return Response(
            {"message": "Failed to create user therapy info.", "data": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


from django.db.models import Count


class UserScoreRecordsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        user = request.user
        # Annotate score records with the count of selected_emotions
        score_records = ScoreRecord.objects.filter(user=user).annotate(
            num_selected_emotions=Count('selected_emotions')
        ).filter(num_selected_emotions__gt=0)

        if not score_records.exists():
            return Response(
                {"message": "No score records for the user.", "data": []},
                status=status.HTTP_200_OK
            )

        serializer = ScoreRecordSerializer(score_records, many=True)
        return Response(
            {"message": "Score records retrieved successfully.", "data": serializer.data},
            status=status.HTTP_200_OK
        )


class UserProfileUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, *args, **kwargs):
        user = request.user
        data = request.data.copy()

        # Log the incoming request data
        logger.debug(f"Request data: {data}")

        # Ensure that name and email are not mixed up
        if 'name' in data and data['name'] == user.email:
            response = {"message": "name cannot be the same as email.", "data": {}}
            logger.debug(f"Response: {response}")
            return Response(
                response,
                status=status.HTTP_400_BAD_REQUEST
            )

        if 'image' in data and data['image'] is not None:
            try:
                image = data['image']
                img = Image.open(image)

                # Log the image mode and format
                logger.debug(f"Image mode: {img.mode}, Image format: {img.format}")

                # Resize the image while maintaining its format
                img = img.resize((200, 200), Image.LANCZOS)
                buffer = BytesIO()
                img_format = img.format if img.format else 'JPEG'  # Use original format or default to JPEG
                img.save(buffer, format=img_format)
                image_file = ContentFile(buffer.getvalue(), name=image.name)
                data['image'] = image_file
            except Exception as e:
                error_message = f"Failed to process image: {str(e)}"
                logger.error(error_message)
                return Response(
                    {"message": error_message, "data": {}},
                    status=status.HTTP_400_BAD_REQUEST
                )

        serializer = UserProfileUpdateSerializer(user, data=data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            response_data = {
                "message": "Profile updated successfully.",
                "data": serializer.data,
            }
            logger.debug(f"Response: {response_data}")
            return Response(
                response_data,
                status=status.HTTP_200_OK
            )
        else:
            error_message = {"message": "Failed to update profile.", "data": serializer.errors}
            logger.debug(f"Response: {error_message}")
            return Response(
                error_message,
                status=status.HTTP_400_BAD_REQUEST
            )


class GoogleLogin(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        name = request.data.get('name')

        if not email or not name:
            return Response({'message': 'Email and name are required', 'data': {}}, status=status.HTTP_400_BAD_REQUEST)

        user, created = CustomUser.objects.get_or_create(email=email, defaults={'name': name})
        if created:
            user.set_unusable_password()
            user.save()

        refresh = RefreshToken.for_user(user)
        subscription = Subscription.objects.filter(user=user).order_by('-created_at').first()
        subscription_data = SubscriptionDetailSerializer(subscription).data if subscription else None

        # Check isTrialValid logic
        is_trial_valid = None
        if subscription:
            if subscription.subscription == "free":
                if subscription.is_active and subscription.expiry_date >= timezone.now().date():
                    is_trial_valid = True
                else:
                    is_trial_valid = False

        data = {
            "refresh_token": str(refresh),
            "access_token": str(refresh.access_token),
            "email": email,
            "name": user.name,
            "user_id": user.id,
            "image": request.build_absolute_uri(user.image.url) if user.image else None,
            "subscription": subscription_data,
            "isTrialValid": is_trial_valid,
        }
        return Response({"message": "Login successful", "data": data}, status=status.HTTP_200_OK)


class AppleLogin(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        apple_id = request.data.get('id')
        email = request.data.get('email')
        name = request.data.get('name')

        if not apple_id:
            return Response({'message': 'Apple ID is required', 'data': {}}, status=status.HTTP_400_BAD_REQUEST)

        user = CustomUser.objects.filter(uid=apple_id).first()
        if not user:
            if not email or not name:
                return Response({'message': 'Email and name are required for the first time login', 'data': {}},
                                status=status.HTTP_400_BAD_REQUEST)
            user = CustomUser.objects.filter(email=email).first()
            if user:
                user.uid = apple_id
                user.save()
            else:
                user = CustomUser.objects.create(email=email, name=name, uid=apple_id)
                user.set_unusable_password()
                user.save()

        refresh = RefreshToken.for_user(user)
        subscription = Subscription.objects.filter(user=user).order_by('-created_at').first()
        subscription_data = SubscriptionDetailSerializer(subscription).data if subscription else None

        # Check isTrialValid logic
        is_trial_valid = None
        if subscription:
            if subscription.subscription == "free":
                if subscription.is_active and subscription.expiry_date >= timezone.now().date():
                    is_trial_valid = True
                else:
                    is_trial_valid = False

        data = {
            "refresh_token": str(refresh),
            "access_token": str(refresh.access_token),
            "email": user.email,
            "name": user.name,
            "user_id": user.id,
            "image": request.build_absolute_uri(user.image.url) if user.image else None,
            "subscription": subscription_data,
            "isTrialValid": is_trial_valid,
        }
        return Response({"message": "Login successful", "data": data}, status=status.HTTP_200_OK)
