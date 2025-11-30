from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from aiomarzban import MarzbanAPI, UserDataLimitResetStrategy
from sqlalchemy import select

from app.repo.models import MarzbanInstance
from app.repo.db import get_session
from app.utils.logging import get_logger
from config import MAX_IPS_PER_CONFIG

LOG = get_logger(__name__)


@dataclass
class NodeLoadMetrics:
    node_id: int
    node_name: str
    active_users: int
    usage_coefficient: float
    uplink: int
    downlink: int
    instance_id: str

    @property
    def load_score(self) -> float:
        total_traffic_gb = (self.uplink + self.downlink) / (1024 ** 3)

        user_weight = 100.0
        traffic_weight = 1.0

        score = (
            (self.active_users * user_weight * self.usage_coefficient) +
            (total_traffic_gb * traffic_weight)
        )

        return score


class MarzbanClient:
    def __init__(self):
        self._instances_cache: Dict[str, MarzbanAPI] = {}

    async def _get_active_instances(self) -> List[MarzbanInstance]:
        async with get_session() as session:
            result = await session.execute(
                select(MarzbanInstance)
                .where(MarzbanInstance.is_active == True)
                .order_by(MarzbanInstance.priority.asc())
            )
            return list(result.scalars().all())

    def _get_or_create_api(self, instance: MarzbanInstance) -> MarzbanAPI:
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
        from app.utils.redis import get_redis
        import json

        redis_key = f"marzban:{instance.id}:node_metrics"

        try:
            redis = await get_redis()
            cached = await redis.get(redis_key)
            if cached:
                cached_data = json.loads(cached)
                return [
                    NodeLoadMetrics(
                        node_id=m['node_id'],
                        node_name=m['node_name'],
                        active_users=m['active_users'],
                        usage_coefficient=m['usage_coefficient'],
                        uplink=m['uplink'],
                        downlink=m['downlink'],
                        instance_id=m['instance_id']
                    )
                    for m in cached_data
                ]
        except Exception as e:
            LOG.warning(f"Redis error reading node metrics for {instance.id}: {e}")

        try:
            try:
                nodes = await api.get_nodes()
            except Exception as e:
                LOG.debug(f"Nodes API not available for instance {instance.id}: {e}")
                return []

            excluded_names = instance.excluded_node_names or []
            if excluded_names:
                original_count = len(nodes)
                nodes = [n for n in nodes if n.name not in excluded_names]
                if len(nodes) < original_count:
                    LOG.info(f"Excluded {original_count - len(nodes)} node(s) from instance {instance.id}: {excluded_names}")

            if not nodes:
                LOG.warning(f"All nodes excluded for instance {instance.id}")
                return []

            usage_map = {}
            try:
                usage_response = await api.get_nodes_usage()
                usage_map = {
                    u.node_id: u for u in usage_response.usages
                    if u.node_id is not None
                }
            except Exception as e:
                LOG.debug(f"Node usage API not available for instance {instance.id}: {e}")

            try:
                users = await api.get_users(limit=10000)
                total_active_users = sum(1 for u in users.users if u.status == 'active')
            except Exception as e:
                LOG.debug(f"Failed to get users for instance {instance.id}: {e}")
                total_active_users = 0

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
                    active_users=int(avg_users_per_node),
                    usage_coefficient=node.usage_coefficient or 1.0,
                    uplink=uplink,
                    downlink=downlink,
                    instance_id=instance.id
                ))

            try:
                redis = await get_redis()
                cache_data = [
                    {
                        'node_id': m.node_id,
                        'node_name': m.node_name,
                        'active_users': m.active_users,
                        'usage_coefficient': m.usage_coefficient,
                        'uplink': m.uplink,
                        'downlink': m.downlink,
                        'instance_id': m.instance_id
                    }
                    for m in metrics
                ]
                await redis.setex(redis_key, 120, json.dumps(cache_data))
            except Exception as e:
                LOG.warning(f"Redis error caching node metrics for {instance.id}: {e}")

            return metrics

        except Exception as e:
            LOG.error(f"Failed to get node metrics for instance {instance.id}: {e}")
            return []

    async def get_best_instance_and_node(
        self,
        manual_instance_id: Optional[str] = None
    ) -> Tuple[MarzbanInstance, MarzbanAPI, Optional[int]]:
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
        data_limit: int = 300,
        max_ips: Optional[int] = None,
        manual_instance_id: Optional[str] = None
    ):
        """
        Create a new VPN user on the least loaded node.

        Args:
            username: Unique username for the user
            days: Subscription duration in days
            data_limit: Traffic limit in GB
            max_ips: Maximum concurrent IPs (devices) allowed. Defaults to MAX_IPS_PER_CONFIG from config
            manual_instance_id: Optional instance ID for manual selection

        Returns:
            User object from Marzban API with subscription links

        Raises:
            ValueError: If user creation fails or no instances available
        """
        instance, api, node_id = await self.get_best_instance_and_node(manual_instance_id)

        # Use default from config if not specified
        if max_ips is None:
            max_ips = MAX_IPS_PER_CONFIG

        try:
            # Note: aiomarzban v1.0.3 doesn't support ip_limit in UserCreate model
            # We need to manually add it to the request payload

            # First, prepare the user data using the standard method
            from aiomarzban.models import UserCreate, UserStatusCreate
            from aiomarzban.utils import future_unix_time, gb_to_bytes
            from aiomarzban.enums import Methods

            expire = future_unix_time(days=days)

            # Create the user data model
            user_data = UserCreate(
                proxies=api.default_proxies,
                expire=expire,
                data_limit=gb_to_bytes(data_limit),
                data_limit_reset_strategy=UserDataLimitResetStrategy.month,
                inbounds=api.default_inbounds,
                username=username,
                status=UserStatusCreate.active,
            )

            # Convert to dict and add ip_limit (not supported by aiomarzban model)
            payload = user_data.model_dump()
            payload['ip_limit'] = max_ips

            # Make the request directly using the API's internal method
            resp = await api._request(Methods.POST, "/user", data=payload)

            # Parse response manually
            from aiomarzban.models import UserResponse
            new_user = UserResponse(**resp)

            if not new_user.links:
                raise ValueError("No VLESS link returned from Marzban")

            LOG.info(
                f"Created user {username} on instance {instance.id} "
                f"(target node: {node_id if node_id else 'auto'}, max_ips: {max_ips})"
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
        max_ips: Optional[int] = None,
        **kwargs
    ):
        """
        Modify user settings in Marzban.

        Args:
            username: Username to modify
            instance_id: If known, specify the instance; otherwise tries all instances
            max_ips: Maximum concurrent IPs (devices) allowed
            **kwargs: Parameters to update (expire, data_limit, etc.)
        """
        if instance_id:
            instances = [inst for inst in await self._get_active_instances() if inst.id == instance_id]
        else:
            instances = await self._get_active_instances()

        for instance in instances:
            try:
                api = self._get_or_create_api(instance)

                # If max_ips is specified, we need to add it to the payload manually
                if max_ips is not None:
                    from aiomarzban.models import UserModify
                    from aiomarzban.utils import gb_to_bytes
                    from aiomarzban.enums import Methods

                    # Convert data_limit to bytes if present
                    if 'data_limit' in kwargs and kwargs['data_limit'] is not None:
                        kwargs['data_limit'] = gb_to_bytes(kwargs['data_limit'])

                    # Create UserModify model
                    user_data = UserModify(**kwargs)

                    # Convert to dict and add ip_limit
                    payload = user_data.model_dump(exclude_none=True)
                    payload['ip_limit'] = max_ips

                    # Make request directly
                    await api._request(Methods.PUT, f"/user/{username}", data=payload)
                    LOG.info(f"Modified user {username} on instance {instance.id} (max_ips: {max_ips})")
                else:
                    # Use standard method if no ip_limit needed
                    await api.modify_user(username, **kwargs)
                    LOG.info(f"Modified user {username} on instance {instance.id}")

                return
            except Exception:
                continue

        raise ValueError(f"User {username} not found on any instance")
