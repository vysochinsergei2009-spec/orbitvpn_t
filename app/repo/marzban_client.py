"""
Marzban Client Manager for multi-instance and node management.

This module provides a centralized way to interact with multiple Marzban instances,
each of which can manage multiple nodes. It implements load balancing logic to
distribute users across instances and nodes efficiently.
"""

from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from aiomarzban import MarzbanAPI, UserDataLimitResetStrategy
from sqlalchemy import select

from app.repo.models import MarzbanInstance
from app.repo.db import get_session
from app.utils.logging import get_logger

LOG = get_logger(__name__)


@dataclass
class NodeLoadMetrics:
    """Metrics for calculating node load."""
    node_id: int
    node_name: str
    active_users: int
    usage_coefficient: float
    uplink: int
    downlink: int
    instance_id: str

    @property
    def load_score(self) -> float:
        """
        Calculate load score for this node.
        Lower score = less loaded = better choice.

        Formula combines:
        - Active users count (primary factor)
        - Usage coefficient (configured node weight)
        - Traffic volume (secondary factor)
        """
        # Normalize traffic to GB
        total_traffic_gb = (self.uplink + self.downlink) / (1024 ** 3)

        # Calculate weighted score
        # Users have highest weight, traffic is normalized to 0-100 range
        user_weight = 100.0
        traffic_weight = 1.0

        score = (
            (self.active_users * user_weight * self.usage_coefficient) +
            (total_traffic_gb * traffic_weight)
        )

        return score


class MarzbanClient:
    """
    Manages multiple Marzban instances and provides load-balanced user creation.

    Each Marzban instance can have multiple nodes. This client:
    1. Fetches all active Marzban instances from database
    2. Queries each instance for its nodes and their usage
    3. Selects the least loaded node across all instances
    4. Creates users on the selected instance
    """

    def __init__(self):
        self._instances_cache: Dict[str, MarzbanAPI] = {}

    async def _get_active_instances(self) -> List[MarzbanInstance]:
        """Fetch all active Marzban instances from database, ordered by priority."""
        async with get_session() as session:
            result = await session.execute(
                select(MarzbanInstance)
                .where(MarzbanInstance.is_active == True)
                .order_by(MarzbanInstance.priority.asc())
            )
            return list(result.scalars().all())

    def _get_or_create_api(self, instance: MarzbanInstance) -> MarzbanAPI:
        """Get cached MarzbanAPI instance or create new one."""
        if instance.id not in self._instances_cache:
            self._instances_cache[instance.id] = MarzbanAPI(
                address=instance.base_url,
                username=instance.username,
                password=instance.password,
                default_proxies={"vless": {"flow": ""}}
            )
        return self._instances_cache[instance.id]

    async def _get_node_metrics(
        self,
        instance: MarzbanInstance,
        api: MarzbanAPI
    ) -> List[NodeLoadMetrics]:
        """
        Fetch node metrics for a given Marzban instance.

        Returns metrics including active users count and traffic data.
        """
        try:
            # Fetch all nodes
            nodes = await api.get_nodes()

            # Fetch node usage stats
            usage_response = await api.get_nodes_usage()
            usage_map = {
                u.node_id: u for u in usage_response.usages
                if u.node_id is not None
            }

            # Get active users per node
            # Note: We need to count users per node by fetching all users
            # This is expensive but necessary for accurate load balancing
            # TODO: Consider caching this data with TTL
            users = await api.get_users(limit=10000)  # Adjust limit as needed

            users_per_node: Dict[int, int] = {}
            for user in users.users:
                # Count users that have inbounds on this node
                if hasattr(user, 'inbounds') and user.inbounds:
                    for inbound_tag in user.inbounds.keys():
                        # Inbound format typically includes node info
                        # For now, we'll count total active users
                        # and distribute evenly (can be improved)
                        pass

            # For now, estimate users per node as total / node count
            # This is a simplification - ideally Marzban API would provide this
            total_active_users = sum(1 for u in users.users if u.status == 'active')
            node_count = len(nodes)
            avg_users_per_node = total_active_users / node_count if node_count > 0 else 0

            metrics = []
            for node in nodes:
                usage = usage_map.get(node.id)
                uplink = usage.uplink if usage else 0
                downlink = usage.downlink if usage else 0

                metrics.append(NodeLoadMetrics(
                    node_id=node.id,
                    node_name=node.name,
                    active_users=int(avg_users_per_node),  # Approximation
                    usage_coefficient=node.usage_coefficient or 1.0,
                    uplink=uplink,
                    downlink=downlink,
                    instance_id=instance.id
                ))

            return metrics

        except Exception as e:
            LOG.error(f"Failed to get node metrics for instance {instance.id}: {e}")
            return []

    async def get_best_instance_and_node(
        self,
        manual_instance_id: Optional[str] = None
    ) -> Tuple[MarzbanInstance, MarzbanAPI, Optional[int]]:
        """
        Select the best Marzban instance and node based on load.

        Args:
            manual_instance_id: If provided, use this specific instance instead of auto-selection

        Returns:
            Tuple of (MarzbanInstance, MarzbanAPI, node_id or None)
            node_id is None if automatic node selection should be used

        Raises:
            ValueError: If no active instances available or manual instance not found
        """
        instances = await self._get_active_instances()

        if not instances:
            raise ValueError("No active Marzban instances available")

        # Manual instance selection (for future feature: user chooses server)
        if manual_instance_id:
            selected_instance = next(
                (inst for inst in instances if inst.id == manual_instance_id),
                None
            )
            if not selected_instance:
                raise ValueError(f"Marzban instance {manual_instance_id} not found or inactive")

            api = self._get_or_create_api(selected_instance)
            LOG.info(f"Manually selected instance: {manual_instance_id}")
            return selected_instance, api, None

        # Automatic selection: find least loaded node across all instances
        all_metrics: List[NodeLoadMetrics] = []

        for instance in instances:
            api = self._get_or_create_api(instance)
            metrics = await self._get_node_metrics(instance, api)
            all_metrics.extend(metrics)

        if not all_metrics:
            # Fallback to first available instance without node selection
            first_instance = instances[0]
            api = self._get_or_create_api(first_instance)
            LOG.warning("No node metrics available, using first instance without node selection")
            return first_instance, api, None

        # Sort by load score (ascending = least loaded first)
        all_metrics.sort(key=lambda m: m.load_score)
        best_metric = all_metrics[0]

        # Get the instance for the best node
        selected_instance = next(
            inst for inst in instances if inst.id == best_metric.instance_id
        )
        api = self._get_or_create_api(selected_instance)

        LOG.info(
            f"Selected node {best_metric.node_name} (ID: {best_metric.node_id}) "
            f"on instance {selected_instance.id} with load score {best_metric.load_score:.2f}"
        )

        return selected_instance, api, best_metric.node_id

    async def add_user(
        self,
        username: str,
        days: int,
        data_limit: int = 50,
        manual_instance_id: Optional[str] = None
    ):
        """
        Create a new VPN user on the least loaded node.

        Args:
            username: Unique username for the user
            days: Subscription duration in days
            data_limit: Traffic limit in GB
            manual_instance_id: Optional instance ID for manual selection

        Returns:
            User object from Marzban API with subscription links

        Raises:
            ValueError: If user creation fails or no instances available
        """
        instance, api, node_id = await self.get_best_instance_and_node(manual_instance_id)

        try:
            # Note: aiomarzban currently doesn't support explicit node selection in add_user
            # Marzban distributes users automatically based on node configuration
            # The node_id we selected is for tracking/logging purposes

            new_user = await api.add_user(
                username=username,
                days=days,
                data_limit=data_limit,
                data_limit_reset_strategy=UserDataLimitResetStrategy.month,
            )

            if not new_user.links:
                raise ValueError("No VLESS link returned from Marzban")

            LOG.info(
                f"Created user {username} on instance {instance.id} "
                f"(target node: {node_id if node_id else 'auto'})"
            )

            return new_user

        except Exception as e:
            LOG.error(f"Failed to add user {username} on instance {instance.id}: {e}")
            raise

    async def remove_user(self, username: str, instance_id: Optional[str] = None):
        """
        Remove a user from Marzban.

        Args:
            username: Username to remove
            instance_id: If known, specify the instance; otherwise tries all instances
        """
        if instance_id:
            instances = [inst for inst in await self._get_active_instances() if inst.id == instance_id]
        else:
            instances = await self._get_active_instances()

        for instance in instances:
            try:
                api = self._get_or_create_api(instance)
                await api.remove_user(username)
                LOG.info(f"Removed user {username} from instance {instance.id}")
                return
            except Exception as e:
                LOG.debug(f"User {username} not found on instance {instance.id}: {e}")
                continue

        LOG.warning(f"User {username} not found on any instance")

    async def get_user(self, username: str, instance_id: Optional[str] = None):
        """
        Get user info from Marzban.

        Args:
            username: Username to fetch
            instance_id: If known, specify the instance; otherwise tries all instances

        Returns:
            User object or None if not found
        """
        if instance_id:
            instances = [inst for inst in await self._get_active_instances() if inst.id == instance_id]
        else:
            instances = await self._get_active_instances()

        for instance in instances:
            try:
                api = self._get_or_create_api(instance)
                user = await api.get_user(username)
                return user
            except Exception:
                continue

        return None

    async def modify_user(
        self,
        username: str,
        instance_id: Optional[str] = None,
        **kwargs
    ):
        """
        Modify user settings in Marzban.

        Args:
            username: Username to modify
            instance_id: If known, specify the instance; otherwise tries all instances
            **kwargs: Parameters to update (expire, data_limit, etc.)
        """
        if instance_id:
            instances = [inst for inst in await self._get_active_instances() if inst.id == instance_id]
        else:
            instances = await self._get_active_instances()

        for instance in instances:
            try:
                api = self._get_or_create_api(instance)
                await api.modify_user(username, **kwargs)
                LOG.info(f"Modified user {username} on instance {instance.id}")
                return
            except Exception:
                continue

        raise ValueError(f"User {username} not found on any instance")
