from common.server import A2AServer
from common.types import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError
from task_manager import AgentTaskManager
from agent import BookingAgent
import click
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option("--host", default="localhost")
@click.option("--port", default=10003)
def main(host, port):
    try:
        # if not os.getenv("GOOGLE_API_KEY"):
        #         raise MissingAPIKeyError("GOOGLE_API_KEY environment variable not set.")
        
        capabilities = AgentCapabilities(streaming=True)
        skill = AgentSkill(
            id="process_booking",
            name="Process Booking Tool",
            description="Helps with the appointment booking process for users given the customers' available dates, contacts (email, zalo phone number) and location of the appointment.",
            tags=["booking"],
            examples=["Can I book an appointment tomorrow in Thu Duc to cure my toothache?"],
        )
        agent_card = AgentCard(
            name="Appointment Booking Agent",
            description="This agent handles the appointment booking process for the patients/customers given the customers' available dates, contacts (email, zalo phone number) and location of the appointment.",
            url=f"http://{host}:{port}/",
            version="1.0.0",
            defaultInputModes=BookingAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=BookingAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=BookingAgent()),
            host=host,
            port=port,
        )
        server.start()
    except MissingAPIKeyError as e:
        logger.error(f"Error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}")
        exit(1)
    
if __name__ == "__main__":
    print("Start BookingAgent")
    main()

