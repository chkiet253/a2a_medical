from __future__ import annotations
import json
import random
from typing import Any, AsyncIterable, Dict, Optional
from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

from tools import find_today_tool, find_available_shift_tool, save_tool

# Local cache of created request_ids for demo purposes.
request_ids = set()

def create_request_form(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    email: Optional[str] = None,
    zalo_phone: Optional[str] = None, 
    location: Optional[str] = None) -> dict[str, Any]:
  """
   Create a request form for the employee to fill out.
   
   Args:
       date (str): The date of the request. Can be an empty string.
       amount (str): The requested amount. Can be an empty string.
       purpose (str): The purpose of the request. Can be an empty string.
       
   Returns:
       dict[str, Any]: A dictionary containing the request form data.
   """
  request_id = "request_id_" + str(random.randint(1000000, 9999999))
  request_ids.add(request_id)
  return {
      "request_id": request_id,
      "from_date": "<available date (start)>" if not from_date else from_date,
      "to_date": "<available date (end)>" if not to_date else to_date,
      "email": "<email>" if not email else email,
      "zalo_phone": "<zalo phone number>" if not zalo_phone else zalo_phone,
      "location": "<hospital location>" if not location else location,
  }

def return_form(
    form_request: dict[str, Any],    
    tool_context: ToolContext,
    instructions: Optional[str] = None) -> dict[str, Any]:
  """
   Returns a structured json object indicating a form to complete.
   
   Args:
       form_request (dict[str, Any]): The request form data.
       tool_context (ToolContext): The context in which the tool operates.
       instructions (str): Instructions for processing the form. Can be an empty string.       
       
   Returns:
       dict[str, Any]: A JSON dictionary for the form response.
   """  
  if isinstance(form_request, str):
    form_request = json.loads(form_request)

  tool_context.actions.skip_summarization = True
  tool_context.actions.escalate = True
  form_dict = {
      'type': 'form',
      'form': {
        'type': 'object',
        'properties': {
            'from_date': {
                'type': 'string',
                'format': 'date',
                'description': 'Date of expense',
                'title': 'Start Date',
            },
            'to_date': {
                'type': 'string',
                'format': 'date',
                'description': 'Date of expense',
                'title': 'End Date',
            },
            'email': {
                'type': 'string',
                'description': 'Email of customer',
                'title': 'Email',
            },
            'zalo_phone': {
                'type': 'string',
                'format': 'number',
                'description': 'Zalo phone number of customer',
                'title': 'Zalo Phone Number',
            },
            'location': {
                'type': 'string',
                'description': 'Hospital location',
                'title': 'Hospital Location',
            },
            'request_id': {
                'type': 'string',
                'description': 'Request id',
                'title': 'Request ID',
            },
        },
        'required': list(form_request.keys()),
      },
      'form_data': form_request,
      'instructions': instructions,
  }
  return json.dumps(form_dict)

# Hàm để test, không dùng
def book(request_id: str) -> dict[str, Any]:
  """Book the appointment of the customer for a given request_id."""
  print(f"Book request_id: {request_id}")
  if request_id not in request_ids:
    print(f"Invalid request_id: {request_id}")
    return {"request_id": request_id, "status": "Error: Invalid request_id."}
  return {"request_id": request_id, "status": "approved"}


class BookingAgent:
  """An agent that handles appointment booking requests."""

  SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

  def __init__(self):
    self._agent = self._build_agent()
    self._user_id = "remote_agent"
    # Runner để chạy agent và lưu session/memory
    # Hiện tại sử dụng InMemory services để lưu trữ tạm thời (chạy nhanh cho demo).
    # Trong production, nên sử dụng persistent storage (DB, file store) cho artifact/session/memory
    self._runner = Runner(
        app_name=self._agent.name,
        agent=self._agent,
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )

  def invoke(self, query, session_id) -> str:
    # session là một chat giữa user và agent
    session = self._runner.session_service.get_session(
        app_name=self._agent.name, user_id=self._user_id, session_id=session_id
    )
    # content là message từ user gửi đến agent
    content = types.Content(
        role="user", parts=[types.Part.from_text(text=query)]
    )
    if session is None:
      session = self._runner.session_service.create_session(
          app_name=self._agent.name,
          user_id=self._user_id,
          state={},
          session_id=session_id,
      )
    # events mô tả một bước trong quá trình: partial updates, function calls, final response...
    events = self._runner.run(
        user_id=self._user_id, session_id=session.id, new_message=content
    )
    print(f"Events: {events}")
    if not events or not events[-1].content or not events[-1].content.parts:
      return ""
    # Trả về event cuối cùng (final response) dưới dạng text
    return "\n".join([p.text for p in events[-1].content.parts if p.text])

  # Khi model/runner có thể phát partial outputs (ví dụ streaming token hoặc trạng thái trung gian)
  # client UI có thể hiển thị progress/partial result cho người dùng trong thời gian thực.
  # Nhìn chung: Gần giống như invoke(), nhưng trả về một async iterable để client có thể lắng nghe các updates
  # và hiển thị chúng trong thời gian thực.
  async def stream(self, query, session_id) -> AsyncIterable[Dict[str, Any]]:
    session = await self._runner.session_service.get_session(
        app_name=self._agent.name, user_id=self._user_id, session_id=session_id
    )
    content = types.Content(
        role="user", parts=[types.Part.from_text(text=query)]
    )
    if session is None:
      session = await self._runner.session_service.create_session(
          app_name=self._agent.name,
          user_id=self._user_id,
          state={},
          session_id=session_id,
      )
    async for event in self._runner.run_async(
        user_id=self._user_id, session_id=session.id, new_message=content
    ):
      if event.is_final_response():
        response = ""
        if (
            event.content
            and event.content.parts
            and event.content.parts[0].text
        ):
          response = "\n".join([p.text for p in event.content.parts if p.text])
        elif (
            event.content
            and event.content.parts
            and any([True for p in event.content.parts if p.function_response])):
          response = next((p.function_response.model_dump() for p in event.content.parts))
        yield {
            "is_task_complete": True,
            "content": response,
        }
      else:
        yield {
            "is_task_complete": False,
            "updates": "Processing the reimbursement request...",
        }

  def _build_agent(self) -> LlmAgent:
    """Builds the LLM agent for the reimbursement agent."""
    return LlmAgent(
        model="gemini-2.0-flash-001",
        # model=LiteLlm("openai/meta-llama/Llama-3.1-8B-Instruct"),
        name="appointment_booking_agent",
        description=(
            "This agent handles the appointment booking process for the patients/customers"
            " given the customers' available dates, contacts (email, zalo phone number) and location of the appointment."
        ),
        instruction="""
    You are an agent who handle the appointment booking process for patients/customers.

    When you receive an appointment booking request, you should first create a new request form using create_request_form(). Only provide default values if they are provided by the user, otherwise use an empty string as the default value.
    If the user gives a relative day or range (e.g. "tomorrow", "this weekend"), call find_today_tool() to get today's date and convert the input into specific date(s).
      1. 'Start Date': available start time for booking an appointment.
      2. 'End Date': available end time for booking an appointment.
      3. 'Email': the email of the customer.
      4. 'Zalo Phone Number': the zalo phone number of the customer.
      5. 'Location': the location of the hospital.
      P/S: Set 'Start Date' and 'End Date' to be one date if the user only provides one date or day (i.e. 'Tomorrow' returns 'Start Date' and 'End Date' with tomorrow's date).

    Once you created the form, you should return the result of calling return_form with the form data from the create_request_form call.

    Once you received the filled-out form back from the user, you should then check the form contains all required information:
      1. 'Start Date': the start date for booking an appointment.
      2. 'End Date': the end date for booking an appointment.
      3. 'Email': the email of the customer.
      4. 'Zalo Phone Number': the zalo phone number of the customer.
      5. 'Location': the location of the hospital.

    If you don't have all of the information, you should reject the request directly by calling the request_form method, providing the missing fields.

    For valid booking requests, you can then use find_available_shift_tool() to book an appointment. Then save the booking information by calling save_tool().
      * In your response, you should include the request_id and the status of the booking request.

    """,
    # For valid booking requests, you can then use find_available_shift_tool to book an appointment. Then save the booking information by calling save_tool.
        tools=[
            create_request_form,
            find_today_tool,
            find_available_shift_tool,
            save_tool,
            return_form,
        ],
    )