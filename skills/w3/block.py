from typing import Type

import httpx
from langchain.tools.base import ToolException
from pydantic import BaseModel, Field

from utils.chain import ChainType, NetworkTitle, get_network_by_title
from utils.time import TimestampRange

from .base import Web3BaseTool


class GetCurrentBlockInput(BaseModel):
    """
    Input model for fetching the current block info of a network.
    """

    network_title: NetworkTitle = Field(
        ..., description="The network to be used for querying."
    )


class GetCurrentBlockOutput(BaseModel):
    """
    Output model for current block information.
    """

    timestamp: int = Field(..., description="The timestamp of the current block.")
    number: int = Field(..., description="The current block number.")


class GetCurrentBlock(Web3BaseTool):
    """
    This tool returns the block current block information.

    Attributes:
        name (str): Name of the tool, specifically "w3_get_current_block".
        description (str): Comprehensive description of the tool's purpose and functionality.
        args_schema (Type[BaseModel]): Schema for input arguments, specifying expected parameters.
    """

    name: str = "w3_get_current_block"
    description: str = (
        """
        This tool returns the block current block information.
        """
    )
    args_schema: Type[BaseModel] = GetCurrentBlockInput

    def _run(self, network_title: NetworkTitle) -> GetCurrentBlockOutput:
        """
        Run the tool to fetch the the block current block information.

        Args:
            network_title (NetworkTitle): The network to check the block number for.

        Returns:
            GetCurrentBlockOutput: A structured output containing blocks start and end.

        Raises:
            NotImplementedError: This method should not be directly called; use _arun instead.
        """
        raise NotImplementedError("Use _arun instead")

    async def _arun(self, network_title: NetworkTitle) -> GetCurrentBlockOutput:
        """
        Run the tool to fetch the block current block information.

        Args:
            network_title (NetworkTitle): The network to check the block number for.

        Returns:
            GetCurrentBlockOutput: A structured output containing blocks start and end.

        Raises:
            ToolException: If there's an error accessing the RPC or any other issue during the process.
        """

        network = get_network_by_title(network_title)
        chain_type = network.value.chain.value.chain_type
        if chain_type != ChainType.EVM:
            raise ToolException(f"chain type is not supported {chain_type}")

        chain_config = self.chain_provider.get_chain_config(network_title)
        headers = {
            "accept": "application/json",
        }
        try:
            async with httpx.AsyncClient() as client:
                # Get current block number and timestamp
                json_block_number = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_blockNumber",
                    "params": [],
                }
                response_block_number = await client.post(
                    chain_config.rpc_url, headers=headers, json=json_block_number
                )
                response_block_number.raise_for_status()
                current_block_hex = response_block_number.json()["result"]
                current_block = int(current_block_hex, 16)

                json_block_timestamp = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_getBlockByNumber",
                    "params": [
                        current_block_hex,
                        True,
                    ],  # true returns full transaction objects.
                }

                response_block_timestamp = await client.post(
                    chain_config.rpc_url, headers=headers, json=json_block_timestamp
                )
                response_block_timestamp.raise_for_status()
                current_block_timestamp = int(
                    response_block_timestamp.json()["result"]["timestamp"], 16
                )

                return GetCurrentBlockOutput(
                    timestamp=current_block_timestamp, number=current_block
                )
        except httpx.RequestError as req_err:
            raise ToolException(f"request error from RPC API: {req_err}") from req_err
        except httpx.HTTPStatusError as http_err:
            raise ToolException(f"http error from RPC API: {http_err}") from http_err
        except Exception as e:
            raise ToolException(f"error from RPC API: {e}") from e


class GetBlocksBetweenDatesInput(BaseModel):
    """
    Input model for fetching blocks between time range.
    """

    network_title: NetworkTitle = Field(
        ..., description="The network to be used for querying."
    )
    time_range: TimestampRange = Field(
        ...,
        description="""
        The time range to query blocks for, specified as a start and end Unix epoch timestamp.
        The current time MUST be obtained using the 'general_current_epoch_timestamp' tool.
        Calculate the start and end times relative to the current timestamp from 'general_current_epoch_timestamp', for example, to get blocks for the last 7 days, subtract 7 days worth of seconds from the current timestamp for the start time.
        """,
    )


class GetBlocksBetweenDatesOutput(BaseModel):
    """
    Output model for blocks between time range.
    """

    start_block: int = Field(..., description="the start block")
    end_block: int = Field(..., description="the start block")


class GetBlocksBetweenDates(Web3BaseTool):
    """
    This tool returns the block range according to the input timestamps.
    The time_range start and end times MUST be calculated using the current timestamp from the 'general_current_epoch_timestamp' tool.

    Attributes:
        name (str): Name of the tool, specifically "w3_get_block_range_by_time".
        description (str): Comprehensive description of the tool's purpose and functionality.
        args_schema (Type[BaseModel]): Schema for input arguments, specifying expected parameters.
    """

    name: str = "w3_get_block_range_by_time"
    description: str = (
        """
        This tool returns the block range according to the input timestamps.
        The time_range start and end times MUST be calculated using the current timestamp from the 'general_current_epoch_timestamp' tool.
        For example, to get blocks for the last 5 minutes, use the output of 'general_current_epoch_timestamp' to get the current time, subtract 300 seconds (5 minutes) from it to get the start time, and use the current time as the end time.
        """
    )
    args_schema: Type[BaseModel] = GetBlocksBetweenDatesInput

    def _run(
        self, network_title: NetworkTitle, time_range: TimestampRange
    ) -> GetBlocksBetweenDatesOutput:
        """
        Run the tool to fetch the block range according to the input timestamps.
        The time_range start and end times MUST be calculated using the current timestamp from the 'general_current_epoch_timestamp' tool.

        Args:
            network_title (NetworkTitle): The network to check the block number for.
            time_range (TimestampRange): The time range to query blocks for, specified as a start and end Unix epoch timestamp, calculated relative to the current timestamp from 'general_current_epoch_timestamp'.

        Returns:
            GetBlocksBetweenDatesOutput: A structured output containing blocks start and end.

        Raises:
            NotImplementedError: This method should not be directly called; use _arun instead.
        """
        raise NotImplementedError("Use _arun instead")

    async def _arun(
        self, network_title: NetworkTitle, time_range: TimestampRange
    ) -> GetBlocksBetweenDatesOutput:
        """
        Run the tool to fetch the block range according to the input timestamps.
        The time_range start and end times MUST be calculated using the current timestamp from the 'general_current_epoch_timestamp' tool.

        Args:
            network_title (NetworkTitle): The network to check the block number for.
            time_range (TimestampRange): The time range to query blocks for, specified as a start and end Unix epoch timestamp, calculated relative to the current timestamp from 'general_current_epoch_timestamp'.

        Returns:
            GetBlocksBetweenDatesOutput: A structured output containing blocks start and end.

        Raises:
            ToolException: If there's an error accessing the RPC or any other issue during the process.
        """

        network = get_network_by_title(network_title)

        max_block_difference = 10000
        try:
            current_block = await GetCurrentBlock(
                chain_provider=self.chain_provider,
                system_store=self.system_store,
                skill_store=self.skill_store,
                agent_store=self.agent_store,
                agent_id=self.agent_id,
            ).arun(
                tool_input=GetCurrentBlockInput(network_title=network_title).model_dump(
                    exclude_none=True
                )
            )

            # Calculate approximate block numbers
            time_diff_start = current_block.timestamp - time_range.start
            start_block = max(
                0,
                current_block.number - int(time_diff_start / network.value.block_time),
            )

            time_diff_end = current_block.timestamp - time_range.end
            end_block = max(
                0,
                current_block.number - int(time_diff_end / network.value.block_time),
            )

            # Enforce maximum block difference, adjust start block.
            if end_block - start_block > max_block_difference:
                start_block = max(
                    0, end_block - max_block_difference
                )  # prevent negative start block.

            return GetBlocksBetweenDatesOutput(
                start_block=start_block, end_block=end_block
            )
        except httpx.RequestError as req_err:
            raise ToolException(f"request error from RPC API: {req_err}") from req_err
        except httpx.HTTPStatusError as http_err:
            raise ToolException(f"http error from RPC API: {http_err}") from http_err
        except Exception as e:
            raise ToolException(f"error from RPC API: {e}") from e
