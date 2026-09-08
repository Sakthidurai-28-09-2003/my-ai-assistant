import os
import base64
import ast
import markdown
import requests

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import (
    authenticate,
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required

from dotenv import load_dotenv

from .models import Conversation, Message, Profile
from pypdf import PdfReader
from io import BytesIO
from groq import Groq
from django.http import JsonResponse
from django.http import HttpResponse



from rest_framework.decorators import api_view
from rest_framework.response import Response

from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated





load_dotenv()

FREE_MODELS = [
    "dots-studio/dots-3-note-preview:free",
    "google/gemma-4-31b-it:free",
]



def call_ai(api_messages):
    api_key = os.getenv("OPENROUTER_API_KEY")

    last_error = None

    for model in FREE_MODELS:
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": api_messages,
                },
                timeout=60,
            )

            response.raise_for_status()

            data = response.json()

            answer = data["choices"][0]["message"]["content"]

            # Avoid known useless safety-classifier output
            if answer:
                cleaned = answer.strip().lower()

                if (
                    cleaned.startswith("user safety:")
                    or cleaned.startswith("response safety:")
                ):
                    last_error = "Model returned safety classification only."
                    continue

            return answer

        except requests.exceptions.HTTPError as e:
            last_error = (
                f"{model}: HTTP {e.response.status_code} "
                f"{e.response.text}"
            )

            # Try next model on common free-model failures
            if e.response.status_code in [403, 404, 429, 500, 502, 503, 504]:
                continue

            raise

        except Exception as e:
            last_error = f"{model}: {str(e)}"
            continue

    raise Exception(
        f"All free AI models failed. Last error: {last_error}"
    )




def call_vision_ai(api_messages):

    api_key = os.getenv("OPENROUTER_API_KEY")

    vision_models = [
        "minimax/minimax-m3:free",
        "google/gemma-4-26b-a4b-it:free",
    ]

    last_error = None

    for model in vision_models:

        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",

                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },

                json={
                    "model": model,
                    "messages": api_messages,
                },

                timeout=60,
            )

            response.raise_for_status()

            data = response.json()

            answer = data["choices"][0]["message"]["content"]

            if not answer:
                continue

            answer = str(answer).strip()

            # Skip safety-classifier style responses
            cleaned = answer.lower()

            if (
                cleaned.startswith("user safety:")
                or cleaned.startswith("response safety:")
            ):
                last_error = (
                    f"{model} returned safety classification only."
                )
                continue

            return answer

        except Exception as e:
            last_error = f"{model}: {str(e)}"
            continue

    raise Exception(
        f"All vision models failed. {last_error}"
    )


@login_required
def home(request, conversation_id=None):

    conversations = Conversation.objects.filter(
        user=request.user
    ).order_by("-updated_at")

    conversation = None

    if conversation_id:
        conversation = get_object_or_404(
            Conversation,
            id=conversation_id,
            user=request.user
        )

    if request.method == "POST":

        user_message = request.POST.get(
            "message",
            ""
        ).strip()

        uploaded_file = request.FILES.get(
            "attachment"
        )

        image_data = None
        image_mime = None
        file_text = ""

        # ==================================
        # READ UPLOADED FILE
        # ==================================

        if uploaded_file:

            filename = uploaded_file.name.lower()

            # IMAGE
            if uploaded_file.content_type.startswith("image/"):

                image_mime = uploaded_file.content_type

                image_bytes = uploaded_file.read()

                image_data = base64.b64encode(
                    image_bytes
                ).decode("utf-8")

            # PDF
            elif filename.endswith(".pdf"):

                try:
                    reader = PdfReader(uploaded_file)

                    pages = []

                    for page in reader.pages:
                        text = page.extract_text()

                        if text:
                            pages.append(text)

                    file_text = "\n\n".join(pages)

                except Exception:
                    file_text = ""

            # TXT
            elif filename.endswith(".txt"):

                try:
                    file_text = uploaded_file.read().decode(
                        "utf-8",
                        errors="ignore"
                    )

                except Exception:
                    file_text = ""

        # ==================================
        # PROCESS MESSAGE
        # ==================================

        if user_message or uploaded_file:

            # Create conversation
            if conversation is None:

                if user_message:
                    title = user_message[:40]

                elif uploaded_file:
                    title = uploaded_file.name[:40]

                else:
                    title = "New conversation"

                conversation = Conversation.objects.create(
                    user=request.user,
                    title=title
                )

            # ==================================
            # SAVE MESSAGE USER SEES
            # ==================================

            display_message = user_message

            if uploaded_file:

                if display_message:
                    display_message += (
                        f"\n📎 {uploaded_file.name}"
                    )

                else:
                    display_message = (
                        f"📎 {uploaded_file.name}"
                    )

            Message.objects.create(
                conversation=conversation,
                role="user",
                content=user_message,
                attachment=uploaded_file if uploaded_file else None
             )

            # ==================================
            # PREPARE TEXT FOR AI
            # ==================================

            combined_message = user_message

            if file_text:

                combined_message += (
                    "\n\n"
                    "The user uploaded a file. "
                    "Read the content below and answer "
                    "the user's question using it.\n\n"
                    "FILE CONTENT:\n"
                    + file_text[:20000]
                )

            # ==================================
            # BUILD CHAT HISTORY
            # ==================================

            previous_messages = (
                conversation.messages.order_by(
                    "created_at"
                )
            )

            api_messages = [
                {
                    "role": "system",
                    "content": (
                        "You are My AI, the AI assistant inside the My AI application. "
                        "Always identify yourself as My AI. "
                        "Never say that you are Dots, Dots Studio, RedNote, OpenRouter, "
                        "or mention the underlying AI model or provider. "
                        "If the user asks who you are, say that you are My AI, "
                        "an AI assistant designed to help with questions, learning, "
                        "coding, writing, and everyday tasks."
                    )
                }
            ]

            for msg in previous_messages:
                api_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })

            # ==================================
            # REPLACE LATEST USER MESSAGE
            # ==================================

            if api_messages:

                # IMAGE REQUEST
                if image_data:

                    api_messages[-1]["content"] = [
                        {
                            "type": "text",
                            "text": (
                                user_message
                                or "Describe this image."
                            )
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": (
                                    f"data:{image_mime};"
                                    f"base64,{image_data}"
                                )
                            }
                        }
                    ]

                # PDF / TXT / NORMAL TEXT
                else:

                    api_messages[-1]["content"] = (
                        combined_message
                    )

            # ==================================
            # CALL AI
            # ==================================

            try:

                if image_data:

                    ai_text = call_vision_ai(
                        api_messages
                    )

                else:

                    ai_text = call_ai(
                        api_messages
                    )

                Message.objects.create(
                    conversation=conversation,
                    role="assistant",
                    content=ai_text
                )

            except Exception as e:

                # Temporary while developing:
                print("AI ERROR:", str(e))

                Message.objects.create(
                    conversation=conversation,
                    role="assistant",
                    content=(
                        "The AI could not process this request. "
                        "Please try again shortly."
                    )
                )

            return redirect(
                "conversation",
                conversation_id=conversation.id
            )

    # ==================================
    # LOAD CHAT
    # ==================================

    messages = []

    if conversation:

        messages = conversation.messages.order_by(
            "created_at"
        )

        for message in messages:

            if message.role == "assistant":

                message.rendered_content = (
                    markdown.markdown(
                        message.content,
                        extensions=[
                            "fenced_code",
                            "tables"
                        ]
                    )
                )

    # ==================================
    # PROFILE
    # ==================================

    profile, created = Profile.objects.get_or_create(
        user=request.user
    )

    return render(
        request,
        "assistant/home.html",
        {
            "conversations": conversations,
            "conversation": conversation,
            "messages": messages,
            "profile": profile,
        }
    )


def register_view(request):
    error = ""

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if password != confirm_password:
            error = "Passwords do not match."

        elif User.objects.filter(username=username).exists():
            error = "Username already exists."

        elif User.objects.filter(email=email).exists():
            error = "Email already exists."

        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password
            )

            login(request, user)

            return redirect("home")

    return render(
        request,
        "assistant/register.html",
        {
            "error": error
        }
    )


def login_view(request):
    error = ""

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            login(request, user)
            return redirect("home")

        error = "Invalid username or password."

    return render(
        request,
        "assistant/login.html",
        {
            "error": error
        }
    )


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def profile_view(request):

    profile, created = Profile.objects.get_or_create(
        user=request.user
    )

    if request.method == "POST":
        avatar = request.FILES.get("avatar")

        if avatar:
            profile.avatar = avatar
            profile.save()

        return redirect("profile")

    return render(
        request,
        "assistant/profile.html",
        {
            "profile": profile
        }
    )


@login_required
def edit_profile_view(request):
    error = ""
    success = ""

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()

        if not username or not email:
            error = "Username and email are required."

        elif User.objects.exclude(
            id=request.user.id
        ).filter(username=username).exists():

            error = "That username is already taken."

        elif User.objects.exclude(
            id=request.user.id
        ).filter(email=email).exists():

            error = "That email is already in use."

        else:
            request.user.username = username
            request.user.email = email
            request.user.save()

            success = "Profile updated successfully."

    return render(
        request,
        "assistant/edit_profile.html",
        {
            "error": error,
            "success": success
        }
    )


@login_required
def delete_conversation(request, conversation_id):

    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
        user=request.user
    )

    if request.method == "POST":
        conversation.delete()

    return redirect("home")


@login_required
def rename_conversation(request, conversation_id):

    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
        user=request.user
    )

    if request.method == "POST":
        new_title = request.POST.get("title", "").strip()

        if new_title:
            conversation.title = new_title[:200]
            conversation.save()

    return redirect(
        "conversation",
        conversation_id=conversation.id
    )


@login_required
def settings_view(request):
    error = ""
    success = ""

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "change_password":

            current_password = request.POST.get(
                "current_password",
                ""
            )

            new_password = request.POST.get(
                "new_password",
                ""
            )

            confirm_password = request.POST.get(
                "confirm_password",
                ""
            )

            if not request.user.check_password(current_password):
                error = "Current password is incorrect."

            elif new_password != confirm_password:
                error = "New passwords do not match."

            elif len(new_password) < 6:
                error = "Password must be at least 6 characters."

            else:
                request.user.set_password(new_password)
                request.user.save()

                update_session_auth_hash(
                    request,
                    request.user
                )

                success = "Password changed successfully."

    return render(
        request,
        "assistant/settings.html",
        {
            "error": error,
            "success": success
        }
    )



@login_required
def delete_account_view(request):
    error = ""

    if request.method == "POST":
        password = request.POST.get("password", "")

        if not request.user.check_password(password):
            error = "Incorrect password."

        else:
            user = request.user

            logout(request)

            user.delete()

            return redirect("register")

    return render(
        request,
        "assistant/delete_account.html",
        {
            "error": error
        }
    )



@login_required
def regenerate_response(request, conversation_id):

    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
        user=request.user
    )

    if request.method == "POST":

        messages = conversation.messages.order_by("created_at")

        last_user_message = (
            messages.filter(role="user").last()
        )

        last_ai_message = (
            messages.filter(role="assistant").last()
        )

        if last_user_message:

            if last_ai_message:
                last_ai_message.delete()

            api_messages = []

            for msg in conversation.messages.order_by("created_at"):
                api_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })

            try:
                api_key = os.getenv("OPENROUTER_API_KEY")

                response = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "thinkingmachines/inkling-small:free",
                        "messages": api_messages
                    },
                    timeout=60,
                )

                response.raise_for_status()

                data = response.json()

                ai_text = data["choices"][0]["message"]["content"]

                # Clean escaped line breaks
                if isinstance(ai_text, str):
                    ai_text = ai_text.replace("\\n", "\n")
                    ai_text = ai_text.replace("\\t", "\t")

                    # Remove unwanted tuple/string wrapper
                    if ai_text.startswith("('") and ai_text.endswith("')"):
                        ai_text = ai_text[2:-2]

                    ai_text = ai_text.strip()

                Message.objects.create(
                    conversation=conversation,
                    role="assistant",
                    content=ai_text
                )

            except Exception:
                Message.objects.create(
                    conversation=conversation,
                    role="assistant",
                    content="Could not regenerate the response. Please try again."
                )

    return redirect(
        "conversation",
        conversation_id=conversation.id
    )


@login_required
def transcribe_audio(request):

    if request.method != "POST":
        return JsonResponse(
            {"error": "Invalid request"},
            status=400
        )

    audio_file = request.FILES.get("audio")

    if not audio_file:
        return JsonResponse(
            {"error": "No audio received"},
            status=400
        )

    try:
        client = Groq(
            api_key=os.getenv("GROQ_API_KEY")
        )

        transcription = client.audio.transcriptions.create(
            file=(
                audio_file.name,
                audio_file.read()
            ),
            model="whisper-large-v3-turbo",
            response_format="json",
        )

        return JsonResponse({
            "text": transcription.text
        })

    except Exception as e:
        print("VOICE ERROR:", str(e))

        return JsonResponse(
            {
                "error": "Could not transcribe audio"
            },
            status=500
        )


@login_required
def export_conversation(request, conversation_id):

        conversation = get_object_or_404(
            Conversation,
            id=conversation_id,
            user=request.user
        )

        messages = conversation.messages.order_by("created_at")

        content = f"My AI Conversation\n"
        content += f"Title: {conversation.title}\n\n"

        for message in messages:

            if message.role == "user":
                content += "You:\n"
            else:
                content += "My AI:\n"

            clean_text = message.content

            clean_text = clean_text.replace("**", "")
            clean_text = clean_text.replace("### ", "")
            clean_text = clean_text.replace("## ", "")
            clean_text = clean_text.replace("# ", "")

            content += clean_text
            content += "\n\n"

        response = HttpResponse(
            content,
            content_type="text/plain"
        )

        response[
            "Content-Disposition"
        ] = (
            f'attachment; filename="'
            f'{conversation.title[:30]}.txt"'
        )

        return response






@api_view(["GET"])
def api_test(request):
    return Response({
        "message": "My AI API is working"
    })


@api_view(["POST"])
def api_register(request):

    username = request.data.get("username", "").strip()
    email = request.data.get("email", "").strip()
    password = request.data.get("password", "")

    if not username or not email or not password:
        return Response(
            {
                "error": "Username, email and password are required."
            },
            status=400
        )

    if User.objects.filter(username=username).exists():
        return Response(
            {
                "error": "Username already exists."
            },
            status=400
        )

    if User.objects.filter(email=email).exists():
        return Response(
            {
                "error": "Email already exists."
            },
            status=400
        )

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password
    )

    return Response(
        {
            "message": "Account created successfully.",
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
        },
        status=201
    )

@api_view(["POST"])
def api_login(request):
    username = request.data.get("username", "").strip()
    password = request.data.get("password", "")

    if not username or not password:
        return Response(
            {"error": "Username and password are required."},
            status=400
        )

    user = authenticate(
        username=username,
        password=password
    )

    if user is None:
        return Response(
            {"error": "Invalid username or password."},
            status=400
        )

    token, created = Token.objects.get_or_create(user=user)

    return Response({
        "message": "Login successful.",
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "token": token.key,
    })


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_conversations(request):

    conversations = Conversation.objects.filter(
        user=request.user
    ).order_by("-updated_at")

    data = []

    for chat in conversations:
        data.append({
            "id": chat.id,
            "title": chat.title,
        })

    return Response(data)

@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_create_conversation(request):

    title = request.data.get(
        "title",
        "New Chat"
    ).strip()

    if not title:
        title = "New Chat"

    conversation = Conversation.objects.create(
        user=request.user,
        title=title[:200]
    )

    return Response(
        {
            "id": conversation.id,
            "title": conversation.title,
            "message": "Conversation created successfully."
        },
        status=201
    )

@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_send_message(request, conversation_id):

    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
        user=request.user
    )

    user_message = request.data.get("message", "").strip()

    if not user_message:
        return Response(
            {"error": "Message is required."},
            status=400
        )

    Message.objects.create(
        conversation=conversation,
        role="user",
        content=user_message
    )

    previous_messages = conversation.messages.order_by("created_at")

    api_messages = []

    for msg in previous_messages:
        api_messages.append({
            "role": msg.role,
            "content": msg.content
        })

    try:
        ai_text = call_ai(api_messages)

        Message.objects.create(
            conversation=conversation,
            role="assistant",
            content=ai_text
        )

        return Response({
            "user_message": user_message,
            "ai_response": ai_text
        })

    except Exception:
        return Response(
            {
                "error": "AI service is temporarily unavailable."
            },
            status=503
        )



@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_conversation_messages(request, conversation_id):

    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
        user=request.user
    )

    messages = conversation.messages.order_by("created_at")

    data = []

    for message in messages:
        data.append({
            "id": message.id,
            "role": message.role,
            "content": message.content,
        })

    return Response({
        "conversation_id": conversation.id,
        "title": conversation.title,
        "messages": data,
    })