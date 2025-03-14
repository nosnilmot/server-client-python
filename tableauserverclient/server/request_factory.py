from os import name
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterable, List, Optional, Tuple, TYPE_CHECKING

from requests.packages.urllib3.fields import RequestField
from requests.packages.urllib3.filepost import encode_multipart_formdata

from tableauserverclient.models.metric_item import MetricItem

from ..models import ConnectionItem
from ..models import DataAlertItem
from ..models import FlowItem
from ..models import ProjectItem
from ..models import SiteItem
from ..models import SubscriptionItem
from ..models import TaskItem, UserItem, GroupItem, PermissionsRule, FavoriteItem
from ..models import WebhookItem

if TYPE_CHECKING:
    from ..models import SubscriptionItem
    from ..models import DataAlertItem
    from ..models import FlowItem
    from ..models import ConnectionItem
    from ..models import SiteItem
    from ..models import ProjectItem
    from tableauserverclient.server import Server


def _add_multipart(parts: Dict) -> Tuple[Any, str]:
    mime_multipart_parts = list()
    for name, (filename, data, content_type) in parts.items():
        multipart_part = RequestField(name=name, data=data, filename=filename)
        multipart_part.make_multipart(content_type=content_type)
        mime_multipart_parts.append(multipart_part)
    xml_request, content_type = encode_multipart_formdata(mime_multipart_parts)
    content_type = "".join(("multipart/mixed",) + content_type.partition(";")[1:])
    return xml_request, content_type


def _tsrequest_wrapped(func):
    def wrapper(self, *args, **kwargs) -> bytes:
        xml_request = ET.Element("tsRequest")
        func(self, xml_request, *args, **kwargs)
        return ET.tostring(xml_request)

    return wrapper


def _add_connections_element(connections_element, connection):
    connection_element = ET.SubElement(connections_element, "connection")
    if not connection.server_address:
        raise ValueError("Connection must have a server address")
    connection_element.attrib["serverAddress"] = connection.server_address
    if connection.server_port:
        connection_element.attrib["serverPort"] = connection.server_port
    if connection.connection_credentials:
        connection_credentials = connection.connection_credentials
        _add_credentials_element(connection_element, connection_credentials)


def _add_hiddenview_element(views_element, view_name):
    view_element = ET.SubElement(views_element, "view")
    view_element.attrib["name"] = view_name
    view_element.attrib["hidden"] = "true"


def _add_credentials_element(parent_element, connection_credentials):
    credentials_element = ET.SubElement(parent_element, "connectionCredentials")
    if not connection_credentials.password or not connection_credentials.name:
        raise ValueError("Connection Credentials must have a name and password")
    credentials_element.attrib["name"] = connection_credentials.name
    credentials_element.attrib["password"] = connection_credentials.password
    credentials_element.attrib["embed"] = "true" if connection_credentials.embed else "false"
    if connection_credentials.oauth:
        credentials_element.attrib["oAuth"] = "true"


class AuthRequest(object):
    def signin_req(self, auth_item):
        xml_request = ET.Element("tsRequest")

        credentials_element = ET.SubElement(xml_request, "credentials")
        for attribute_name, attribute_value in auth_item.credentials.items():
            credentials_element.attrib[attribute_name] = attribute_value

        site_element = ET.SubElement(credentials_element, "site")
        site_element.attrib["contentUrl"] = auth_item.site_id

        if auth_item.user_id_to_impersonate:
            user_element = ET.SubElement(credentials_element, "user")
            user_element.attrib["id"] = auth_item.user_id_to_impersonate
        return ET.tostring(xml_request)

    def switch_req(self, site_content_url):
        xml_request = ET.Element("tsRequest")

        site_element = ET.SubElement(xml_request, "site")
        site_element.attrib["contentUrl"] = site_content_url
        return ET.tostring(xml_request)


class ColumnRequest(object):
    def update_req(self, column_item):
        xml_request = ET.Element("tsRequest")
        column_element = ET.SubElement(xml_request, "column")

        if column_item.description:
            column_element.attrib["description"] = str(column_item.description)

        return ET.tostring(xml_request)


class DataAlertRequest(object):
    def add_user_to_alert(self, alert_item: "DataAlertItem", user_id: str) -> bytes:
        xml_request = ET.Element("tsRequest")
        user_element = ET.SubElement(xml_request, "user")
        user_element.attrib["id"] = user_id

        return ET.tostring(xml_request)

    def update_req(self, alert_item: "DataAlertItem") -> bytes:
        xml_request = ET.Element("tsRequest")
        dataAlert_element = ET.SubElement(xml_request, "dataAlert")
        if alert_item.subject is not None:
            dataAlert_element.attrib["subject"] = alert_item.subject
        if alert_item.frequency is not None:
            dataAlert_element.attrib["frequency"] = alert_item.frequency.lower()
        if alert_item.public is not None:
            dataAlert_element.attrib["public"] = str(alert_item.public).lower()

        owner = ET.SubElement(dataAlert_element, "owner")
        if alert_item.owner_id is not None:
            owner.attrib["id"] = alert_item.owner_id

        return ET.tostring(xml_request)


class DatabaseRequest(object):
    def update_req(self, database_item):
        xml_request = ET.Element("tsRequest")
        database_element = ET.SubElement(xml_request, "database")
        if database_item.contact_id:
            contact_element = ET.SubElement(database_element, "contact")
            contact_element.attrib["id"] = database_item.contact_id

        database_element.attrib["isCertified"] = str(database_item.certified).lower()

        if database_item.certification_note:
            database_element.attrib["certificationNote"] = str(database_item.certification_note)

        if database_item.description:
            database_element.attrib["description"] = str(database_item.description)

        return ET.tostring(xml_request)


class DatasourceRequest(object):
    def _generate_xml(self, datasource_item, connection_credentials=None, connections=None):
        xml_request = ET.Element("tsRequest")
        datasource_element = ET.SubElement(xml_request, "datasource")
        datasource_element.attrib["name"] = datasource_item.name
        if datasource_item.description:
            datasource_element.attrib["description"] = str(datasource_item.description)
        if datasource_item.use_remote_query_agent is not None:
            datasource_element.attrib["useRemoteQueryAgent"] = str(datasource_item.use_remote_query_agent).lower()

        if datasource_item.ask_data_enablement:
            ask_data_element = ET.SubElement(datasource_element, "askData")
            ask_data_element.attrib["enablement"] = datasource_item.ask_data_enablement

        project_element = ET.SubElement(datasource_element, "project")
        project_element.attrib["id"] = datasource_item.project_id

        if connection_credentials is not None and connections is not None:
            raise RuntimeError("You cannot set both `connections` and `connection_credentials`")

        if connection_credentials is not None:
            _add_credentials_element(datasource_element, connection_credentials)

        if connections is not None:
            connections_element = ET.SubElement(datasource_element, "connections")
            for connection in connections:
                _add_connections_element(connections_element, connection)
        return ET.tostring(xml_request)

    def update_req(self, datasource_item):
        xml_request = ET.Element("tsRequest")
        datasource_element = ET.SubElement(xml_request, "datasource")
        if datasource_item.name:
            datasource_element.attrib["name"] = datasource_item.name
        if datasource_item.ask_data_enablement:
            ask_data_element = ET.SubElement(datasource_element, "askData")
            ask_data_element.attrib["enablement"] = datasource_item.ask_data_enablement
        if datasource_item.project_id:
            project_element = ET.SubElement(datasource_element, "project")
            project_element.attrib["id"] = datasource_item.project_id
        if datasource_item.owner_id:
            owner_element = ET.SubElement(datasource_element, "owner")
            owner_element.attrib["id"] = datasource_item.owner_id

        datasource_element.attrib["isCertified"] = str(datasource_item.certified).lower()

        if datasource_item.certification_note:
            datasource_element.attrib["certificationNote"] = str(datasource_item.certification_note)
        if datasource_item.encrypt_extracts is not None:
            datasource_element.attrib["encryptExtracts"] = str(datasource_item.encrypt_extracts).lower()

        return ET.tostring(xml_request)

    def publish_req(
        self,
        datasource_item,
        filename,
        file_contents,
        connection_credentials=None,
        connections=None,
    ):
        xml_request = self._generate_xml(datasource_item, connection_credentials, connections)

        parts = {
            "request_payload": ("", xml_request, "text/xml"),
            "tableau_datasource": (filename, file_contents, "application/octet-stream"),
        }
        return _add_multipart(parts)

    def publish_req_chunked(self, datasource_item, connection_credentials=None, connections=None):
        xml_request = self._generate_xml(datasource_item, connection_credentials, connections)

        parts = {"request_payload": ("", xml_request, "text/xml")}
        return _add_multipart(parts)


class DQWRequest(object):
    def add_req(self, dqw_item):
        xml_request = ET.Element("tsRequest")
        dqw_element = ET.SubElement(xml_request, "dataQualityWarning")

        dqw_element.attrib["isActive"] = str(dqw_item.active).lower()
        dqw_element.attrib["isSevere"] = str(dqw_item.severe).lower()

        dqw_element.attrib["type"] = dqw_item.warning_type

        if dqw_item.message:
            dqw_element.attrib["message"] = str(dqw_item.message)

        return ET.tostring(xml_request)

    def update_req(self, dqw_item):
        xml_request = ET.Element("tsRequest")
        dqw_element = ET.SubElement(xml_request, "dataQualityWarning")

        dqw_element.attrib["isActive"] = str(dqw_item.active).lower()
        dqw_element.attrib["isSevere"] = str(dqw_item.severe).lower()

        dqw_element.attrib["type"] = dqw_item.warning_type

        if dqw_item.message:
            dqw_element.attrib["message"] = str(dqw_item.message)

        return ET.tostring(xml_request)


class FavoriteRequest(object):
    def _add_to_req(self, id_: str, target_type: str, label: str) -> bytes:
        """
        <favorite label="...">
        <target_type id="..." />
        </favorite>
        """
        xml_request = ET.Element("tsRequest")
        favorite_element = ET.SubElement(xml_request, "favorite")
        target = ET.SubElement(favorite_element, target_type)
        favorite_element.attrib["label"] = label
        target.attrib["id"] = id_

        return ET.tostring(xml_request)

    def add_datasource_req(self, id_: Optional[str], name: Optional[str]) -> bytes:
        if id_ is None:
            raise ValueError("id must exist to add to favorites")
        if name is None:
            raise ValueError("Name must exist to add to favorites.")
        return self._add_to_req(id_, FavoriteItem.Type.Datasource, name)

    def add_flow_req(self, id_: Optional[str], name: Optional[str]) -> bytes:
        if id_ is None:
            raise ValueError("id must exist to add to favorites")
        if name is None:
            raise ValueError("Name must exist to add to favorites.")
        return self._add_to_req(id_, FavoriteItem.Type.Flow, name)

    def add_project_req(self, id_: Optional[str], name: Optional[str]) -> bytes:
        if id_ is None:
            raise ValueError("id must exist to add to favorites")
        if name is None:
            raise ValueError("Name must exist to add to favorites.")
        return self._add_to_req(id_, FavoriteItem.Type.Project, name)

    def add_view_req(self, id_: Optional[str], name: Optional[str]) -> bytes:
        if id_ is None:
            raise ValueError("id must exist to add to favorites")
        if name is None:
            raise ValueError("Name must exist to add to favorites.")
        return self._add_to_req(id_, FavoriteItem.Type.View, name)

    def add_workbook_req(self, id_: Optional[str], name: Optional[str]) -> bytes:
        if id_ is None:
            raise ValueError("id must exist to add to favorites")
        if name is None:
            raise ValueError("Name must exist to add to favorites.")
        return self._add_to_req(id_, FavoriteItem.Type.Workbook, name)


class FileuploadRequest(object):
    def chunk_req(self, chunk):
        parts = {
            "request_payload": ("", "", "text/xml"),
            "tableau_file": ("file", chunk, "application/octet-stream"),
        }
        return _add_multipart(parts)


class FlowRequest(object):
    def _generate_xml(self, flow_item: "FlowItem", connections: Optional[List["ConnectionItem"]] = None) -> bytes:
        xml_request = ET.Element("tsRequest")
        flow_element = ET.SubElement(xml_request, "flow")
        if flow_item.name is not None:
            flow_element.attrib["name"] = flow_item.name
        project_element = ET.SubElement(flow_element, "project")
        project_element.attrib["id"] = flow_item.project_id

        if connections is not None:
            connections_element = ET.SubElement(flow_element, "connections")
            for connection in connections:
                _add_connections_element(connections_element, connection)
        return ET.tostring(xml_request)

    def update_req(self, flow_item: "FlowItem") -> bytes:
        xml_request = ET.Element("tsRequest")
        flow_element = ET.SubElement(xml_request, "flow")
        if flow_item.project_id:
            project_element = ET.SubElement(flow_element, "project")
            project_element.attrib["id"] = flow_item.project_id
        if flow_item.owner_id:
            owner_element = ET.SubElement(flow_element, "owner")
            owner_element.attrib["id"] = flow_item.owner_id

        return ET.tostring(xml_request)

    def publish_req(
        self,
        flow_item: "FlowItem",
        filename: str,
        file_contents: bytes,
        connections: Optional[List["ConnectionItem"]] = None,
    ) -> Tuple[Any, str]:
        xml_request = self._generate_xml(flow_item, connections)

        parts = {
            "request_payload": ("", xml_request, "text/xml"),
            "tableau_flow": (filename, file_contents, "application/octet-stream"),
        }
        return _add_multipart(parts)

    def publish_req_chunked(self, flow_item, connections=None) -> Tuple[Any, str]:
        xml_request = self._generate_xml(flow_item, connections)

        parts = {"request_payload": ("", xml_request, "text/xml")}
        return _add_multipart(parts)


class GroupRequest(object):
    def add_user_req(self, user_id: str) -> bytes:
        xml_request = ET.Element("tsRequest")
        user_element = ET.SubElement(xml_request, "user")
        user_element.attrib["id"] = user_id
        return ET.tostring(xml_request)

    def create_local_req(self, group_item: GroupItem) -> bytes:
        xml_request = ET.Element("tsRequest")
        group_element = ET.SubElement(xml_request, "group")
        if group_item.name is not None:
            group_element.attrib["name"] = group_item.name
        else:
            raise ValueError("Group name must be populated")
        if group_item.minimum_site_role is not None:
            group_element.attrib["minimumSiteRole"] = group_item.minimum_site_role
        return ET.tostring(xml_request)

    def create_ad_req(self, group_item: GroupItem) -> bytes:
        xml_request = ET.Element("tsRequest")
        group_element = ET.SubElement(xml_request, "group")
        if group_item.name is not None:
            group_element.attrib["name"] = group_item.name
        else:
            raise ValueError("Group name must be populated")
        import_element = ET.SubElement(group_element, "import")
        import_element.attrib["source"] = "ActiveDirectory"
        if group_item.domain_name is None:
            error = "Group Domain undefined."
            raise ValueError(error)

        import_element.attrib["domainName"] = group_item.domain_name
        if group_item.license_mode is not None:
            import_element.attrib["grantLicenseMode"] = group_item.license_mode
        if group_item.minimum_site_role is not None:
            import_element.attrib["siteRole"] = group_item.minimum_site_role
        return ET.tostring(xml_request)

    def update_req(self, group_item: GroupItem, default_site_role: Optional[str] = None) -> bytes:
        # (1/8/2021): Deprecated starting v0.15
        if default_site_role is not None:
            import warnings

            warnings.simplefilter("always", DeprecationWarning)
            warnings.warn(
                'RequestFactory.Group.update_req(...default_site_role="") is deprecated, '
                "please set the minimum_site_role field of GroupItem",
                DeprecationWarning,
            )
            group_item.minimum_site_role = default_site_role

        xml_request = ET.Element("tsRequest")
        group_element = ET.SubElement(xml_request, "group")

        if group_item.name is not None:
            group_element.attrib["name"] = group_item.name
        else:
            raise ValueError("Group name must be populated")
        if group_item.domain_name is not None and group_item.domain_name != "local":
            # Import element is only accepted in the request for AD groups
            import_element = ET.SubElement(group_element, "import")
            import_element.attrib["source"] = "ActiveDirectory"
            import_element.attrib["domainName"] = group_item.domain_name
            if isinstance(group_item.minimum_site_role, str):
                import_element.attrib["siteRole"] = group_item.minimum_site_role
            else:
                raise ValueError("Minimum site role must be provided.")
            if group_item.license_mode is not None:
                import_element.attrib["grantLicenseMode"] = group_item.license_mode
        else:
            # Local group request does not accept an 'import' element
            if group_item.minimum_site_role is not None:
                group_element.attrib["minimumSiteRole"] = group_item.minimum_site_role

        return ET.tostring(xml_request)


class PermissionRequest(object):
    def add_req(self, rules: Iterable[PermissionsRule]) -> bytes:
        xml_request = ET.Element("tsRequest")
        permissions_element = ET.SubElement(xml_request, "permissions")

        for rule in rules:
            grantee_capabilities_element = ET.SubElement(permissions_element, "granteeCapabilities")
            grantee_element = ET.SubElement(grantee_capabilities_element, rule.grantee.tag_name)
            grantee_element.attrib["id"] = rule.grantee.id

            capabilities_element = ET.SubElement(grantee_capabilities_element, "capabilities")
            self._add_all_capabilities(capabilities_element, rule.capabilities)

        return ET.tostring(xml_request)

    def _add_all_capabilities(self, capabilities_element, capabilities_map):
        for name, mode in capabilities_map.items():
            capability_element = ET.SubElement(capabilities_element, "capability")
            capability_element.attrib["name"] = name
            capability_element.attrib["mode"] = mode


class ProjectRequest(object):
    def update_req(self, project_item: "ProjectItem") -> bytes:
        xml_request = ET.Element("tsRequest")
        project_element = ET.SubElement(xml_request, "project")
        if project_item.name:
            project_element.attrib["name"] = project_item.name
        if project_item.description:
            project_element.attrib["description"] = project_item.description
        if project_item.content_permissions:
            project_element.attrib["contentPermissions"] = project_item.content_permissions
        if project_item.parent_id is not None:
            project_element.attrib["parentProjectId"] = project_item.parent_id
        return ET.tostring(xml_request)

    def create_req(self, project_item: "ProjectItem") -> bytes:
        xml_request = ET.Element("tsRequest")
        project_element = ET.SubElement(xml_request, "project")
        project_element.attrib["name"] = project_item.name
        if project_item.description:
            project_element.attrib["description"] = project_item.description
        if project_item.content_permissions:
            project_element.attrib["contentPermissions"] = project_item.content_permissions
        if project_item.parent_id:
            project_element.attrib["parentProjectId"] = project_item.parent_id
        return ET.tostring(xml_request)


class ScheduleRequest(object):
    def create_req(self, schedule_item):
        xml_request = ET.Element("tsRequest")
        schedule_element = ET.SubElement(xml_request, "schedule")
        schedule_element.attrib["name"] = schedule_item.name
        schedule_element.attrib["priority"] = str(schedule_item.priority)
        schedule_element.attrib["type"] = schedule_item.schedule_type
        schedule_element.attrib["executionOrder"] = schedule_item.execution_order
        interval_item = schedule_item.interval_item
        schedule_element.attrib["frequency"] = interval_item._frequency
        frequency_element = ET.SubElement(schedule_element, "frequencyDetails")
        frequency_element.attrib["start"] = str(interval_item.start_time)
        if hasattr(interval_item, "end_time") and interval_item.end_time is not None:
            frequency_element.attrib["end"] = str(interval_item.end_time)
        if hasattr(interval_item, "interval") and interval_item.interval:
            intervals_element = ET.SubElement(frequency_element, "intervals")
            for interval in interval_item._interval_type_pairs():
                expression, value = interval
                single_interval_element = ET.SubElement(intervals_element, "interval")
                single_interval_element.attrib[expression] = value
        return ET.tostring(xml_request)

    def update_req(self, schedule_item):
        xml_request = ET.Element("tsRequest")
        schedule_element = ET.SubElement(xml_request, "schedule")
        if schedule_item.name:
            schedule_element.attrib["name"] = schedule_item.name
        if schedule_item.priority:
            schedule_element.attrib["priority"] = str(schedule_item.priority)
        if schedule_item.execution_order:
            schedule_element.attrib["executionOrder"] = schedule_item.execution_order
        if schedule_item.state:
            schedule_element.attrib["state"] = schedule_item.state

        interval_item = schedule_item.interval_item
        if interval_item is not None:
            if interval_item._frequency:
                schedule_element.attrib["frequency"] = interval_item._frequency
            frequency_element = ET.SubElement(schedule_element, "frequencyDetails")
            frequency_element.attrib["start"] = str(interval_item.start_time)
            if hasattr(interval_item, "end_time") and interval_item.end_time is not None:
                frequency_element.attrib["end"] = str(interval_item.end_time)
            intervals_element = ET.SubElement(frequency_element, "intervals")
            if hasattr(interval_item, "interval"):
                for interval in interval_item._interval_type_pairs():
                    (expression, value) = interval
                    single_interval_element = ET.SubElement(intervals_element, "interval")
                    single_interval_element.attrib[expression] = value
        return ET.tostring(xml_request)

    def _add_to_req(self, id_: Optional[str], target_type: str, task_type: str = TaskItem.Type.ExtractRefresh) -> bytes:
        """
        <task>
          <target_type>
            <workbook/datasource id="..."/>
          </target_type>
        </task>

        """
        if not isinstance(id_, str):
            raise ValueError(f"id_ should be a string, received: {type(id_)}")
        xml_request = ET.Element("tsRequest")
        task_element = ET.SubElement(xml_request, "task")
        task = ET.SubElement(task_element, task_type)
        workbook = ET.SubElement(task, target_type)
        workbook.attrib["id"] = id_

        return ET.tostring(xml_request)

    def add_workbook_req(self, id_: Optional[str], task_type: str = TaskItem.Type.ExtractRefresh) -> bytes:
        return self._add_to_req(id_, "workbook", task_type)

    def add_datasource_req(self, id_: Optional[str], task_type: str = TaskItem.Type.ExtractRefresh) -> bytes:
        return self._add_to_req(id_, "datasource", task_type)

    def add_flow_req(self, id_: Optional[str], task_type: str = TaskItem.Type.RunFlow) -> bytes:
        return self._add_to_req(id_, "flow", task_type)


class SiteRequest(object):
    def update_req(self, site_item: "SiteItem", parent_srv: "Server" = None):
        xml_request = ET.Element("tsRequest")
        site_element = ET.SubElement(xml_request, "site")
        if site_item.name:
            site_element.attrib["name"] = site_item.name
        if site_item.content_url:
            site_element.attrib["contentUrl"] = site_item.content_url
        if site_item.admin_mode:
            site_element.attrib["adminMode"] = site_item.admin_mode
        if site_item.user_quota:
            site_element.attrib["userQuota"] = str(site_item.user_quota)
        if site_item.state:
            site_element.attrib["state"] = site_item.state
        if site_item.storage_quota:
            site_element.attrib["storageQuota"] = str(site_item.storage_quota)
        if site_item.disable_subscriptions is not None:
            site_element.attrib["disableSubscriptions"] = str(site_item.disable_subscriptions).lower()
        if site_item.subscribe_others_enabled is not None:
            site_element.attrib["subscribeOthersEnabled"] = str(site_item.subscribe_others_enabled).lower()
        if site_item.revision_limit:
            site_element.attrib["revisionLimit"] = str(site_item.revision_limit)
        if site_item.revision_history_enabled is not None:
            site_element.attrib["revisionHistoryEnabled"] = str(site_item.revision_history_enabled).lower()
        if site_item.data_acceleration_mode is not None:
            site_element.attrib["dataAccelerationMode"] = str(site_item.data_acceleration_mode).lower()
        if site_item.cataloging_enabled is not None:
            site_element.attrib["catalogingEnabled"] = str(site_item.cataloging_enabled).lower()

        flows_edit = str(site_item.editing_flows_enabled).lower()
        flows_schedule = str(site_item.scheduling_flows_enabled).lower()
        flows_all = str(site_item.flows_enabled).lower()

        self.set_versioned_flow_attributes(flows_all, flows_edit, flows_schedule, parent_srv, site_element, site_item)

        if site_item.allow_subscription_attachments is not None:
            site_element.attrib["allowSubscriptionAttachments"] = str(site_item.allow_subscription_attachments).lower()
        if site_item.guest_access_enabled is not None:
            site_element.attrib["guestAccessEnabled"] = str(site_item.guest_access_enabled).lower()
        if site_item.cache_warmup_enabled is not None:
            site_element.attrib["cacheWarmupEnabled"] = str(site_item.cache_warmup_enabled).lower()
        if site_item.commenting_enabled is not None:
            site_element.attrib["commentingEnabled"] = str(site_item.commenting_enabled).lower()
        if site_item.extract_encryption_mode is not None:
            site_element.attrib["extractEncryptionMode"] = str(site_item.extract_encryption_mode).lower()
        if site_item.request_access_enabled is not None:
            site_element.attrib["requestAccessEnabled"] = str(site_item.request_access_enabled).lower()
        if site_item.run_now_enabled is not None:
            site_element.attrib["runNowEnabled"] = str(site_item.run_now_enabled).lower()
        if site_item.tier_creator_capacity is not None:
            site_element.attrib["tierCreatorCapacity"] = str(site_item.tier_creator_capacity).lower()
        if site_item.tier_explorer_capacity is not None:
            site_element.attrib["tierExplorerCapacity"] = str(site_item.tier_explorer_capacity).lower()
        if site_item.tier_viewer_capacity is not None:
            site_element.attrib["tierViewerCapacity"] = str(site_item.tier_viewer_capacity).lower()
        if site_item.data_alerts_enabled is not None:
            site_element.attrib["dataAlertsEnabled"] = str(site_item.data_alerts_enabled)
        if site_item.commenting_mentions_enabled is not None:
            site_element.attrib["commentingMentionsEnabled"] = str(site_item.commenting_mentions_enabled).lower()
        if site_item.catalog_obfuscation_enabled is not None:
            site_element.attrib["catalogObfuscationEnabled"] = str(site_item.catalog_obfuscation_enabled).lower()
        if site_item.flow_auto_save_enabled is not None:
            site_element.attrib["flowAutoSaveEnabled"] = str(site_item.flow_auto_save_enabled).lower()
        if site_item.web_extraction_enabled is not None:
            site_element.attrib["webExtractionEnabled"] = str(site_item.web_extraction_enabled).lower()
        if site_item.metrics_content_type_enabled is not None:
            site_element.attrib["metricsContentTypeEnabled"] = str(site_item.metrics_content_type_enabled).lower()
        if site_item.notify_site_admins_on_throttle is not None:
            site_element.attrib["notifySiteAdminsOnThrottle"] = str(site_item.notify_site_admins_on_throttle).lower()
        if site_item.authoring_enabled is not None:
            site_element.attrib["authoringEnabled"] = str(site_item.authoring_enabled).lower()
        if site_item.custom_subscription_email_enabled is not None:
            site_element.attrib["customSubscriptionEmailEnabled"] = str(
                site_item.custom_subscription_email_enabled
            ).lower()
        if site_item.custom_subscription_email is not None:
            site_element.attrib["customSubscriptionEmail"] = str(site_item.custom_subscription_email).lower()
        if site_item.custom_subscription_footer_enabled is not None:
            site_element.attrib["customSubscriptionFooterEnabled"] = str(
                site_item.custom_subscription_footer_enabled
            ).lower()
        if site_item.custom_subscription_footer is not None:
            site_element.attrib["customSubscriptionFooter"] = str(site_item.custom_subscription_footer).lower()
        if site_item.ask_data_mode is not None:
            site_element.attrib["askDataMode"] = str(site_item.ask_data_mode)
        if site_item.named_sharing_enabled is not None:
            site_element.attrib["namedSharingEnabled"] = str(site_item.named_sharing_enabled).lower()
        if site_item.mobile_biometrics_enabled is not None:
            site_element.attrib["mobileBiometricsEnabled"] = str(site_item.mobile_biometrics_enabled).lower()
        if site_item.sheet_image_enabled is not None:
            site_element.attrib["sheetImageEnabled"] = str(site_item.sheet_image_enabled).lower()
        if site_item.derived_permissions_enabled is not None:
            site_element.attrib["derivedPermissionsEnabled"] = str(site_item.derived_permissions_enabled).lower()
        if site_item.user_visibility_mode is not None:
            site_element.attrib["userVisibilityMode"] = str(site_item.user_visibility_mode)
        if site_item.use_default_time_zone is not None:
            site_element.attrib["useDefaultTimeZone"] = str(site_item.use_default_time_zone).lower()
        if site_item.time_zone is not None:
            site_element.attrib["timeZone"] = str(site_item.time_zone)
        if site_item.auto_suspend_refresh_enabled is not None:
            site_element.attrib["autoSuspendRefreshEnabled"] = str(site_item.auto_suspend_refresh_enabled).lower()
        if site_item.auto_suspend_refresh_inactivity_window is not None:
            site_element.attrib["autoSuspendRefreshInactivityWindow"] = str(
                site_item.auto_suspend_refresh_inactivity_window
            )

        return ET.tostring(xml_request)

    # server: the site request model changes based on api version
    def create_req(self, site_item: "SiteItem", parent_srv: "Server" = None):
        xml_request = ET.Element("tsRequest")
        site_element = ET.SubElement(xml_request, "site")
        site_element.attrib["name"] = site_item.name
        site_element.attrib["contentUrl"] = site_item.content_url
        if site_item.admin_mode:
            site_element.attrib["adminMode"] = site_item.admin_mode
        if site_item.user_quota:
            site_element.attrib["userQuota"] = str(site_item.user_quota)
        if site_item.storage_quota:
            site_element.attrib["storageQuota"] = str(site_item.storage_quota)
        if site_item.disable_subscriptions is not None:
            site_element.attrib["disableSubscriptions"] = str(site_item.disable_subscriptions).lower()
        if site_item.subscribe_others_enabled is not None:
            site_element.attrib["subscribeOthersEnabled"] = str(site_item.subscribe_others_enabled).lower()
        if site_item.revision_limit:
            site_element.attrib["revisionLimit"] = str(site_item.revision_limit)
        if site_item.data_acceleration_mode is not None:
            site_element.attrib["dataAccelerationMode"] = str(site_item.data_acceleration_mode).lower()

        flows_edit = str(site_item.editing_flows_enabled).lower()
        flows_schedule = str(site_item.scheduling_flows_enabled).lower()
        flows_all = str(site_item.flows_enabled).lower()

        self.set_versioned_flow_attributes(flows_all, flows_edit, flows_schedule, parent_srv, site_element, site_item)

        if site_item.allow_subscription_attachments is not None:
            site_element.attrib["allowSubscriptionAttachments"] = str(site_item.allow_subscription_attachments).lower()
        if site_item.guest_access_enabled is not None:
            site_element.attrib["guestAccessEnabled"] = str(site_item.guest_access_enabled).lower()
        if site_item.cache_warmup_enabled is not None:
            site_element.attrib["cacheWarmupEnabled"] = str(site_item.cache_warmup_enabled).lower()
        if site_item.commenting_enabled is not None:
            site_element.attrib["commentingEnabled"] = str(site_item.commenting_enabled).lower()
        if site_item.revision_history_enabled is not None:
            site_element.attrib["revisionHistoryEnabled"] = str(site_item.revision_history_enabled).lower()
        if site_item.extract_encryption_mode is not None:
            site_element.attrib["extractEncryptionMode"] = str(site_item.extract_encryption_mode).lower()
        if site_item.request_access_enabled is not None:
            site_element.attrib["requestAccessEnabled"] = str(site_item.request_access_enabled).lower()
        if site_item.run_now_enabled is not None:
            site_element.attrib["runNowEnabled"] = str(site_item.run_now_enabled).lower()
        if site_item.tier_creator_capacity is not None:
            site_element.attrib["tierCreatorCapacity"] = str(site_item.tier_creator_capacity).lower()
        if site_item.tier_explorer_capacity is not None:
            site_element.attrib["tierExplorerCapacity"] = str(site_item.tier_explorer_capacity).lower()
        if site_item.tier_viewer_capacity is not None:
            site_element.attrib["tierViewerCapacity"] = str(site_item.tier_viewer_capacity).lower()
        if site_item.data_alerts_enabled is not None:
            site_element.attrib["dataAlertsEnabled"] = str(site_item.data_alerts_enabled).lower()
        if site_item.commenting_mentions_enabled is not None:
            site_element.attrib["commentingMentionsEnabled"] = str(site_item.commenting_mentions_enabled).lower()
        if site_item.catalog_obfuscation_enabled is not None:
            site_element.attrib["catalogObfuscationEnabled"] = str(site_item.catalog_obfuscation_enabled).lower()
        if site_item.flow_auto_save_enabled is not None:
            site_element.attrib["flowAutoSaveEnabled"] = str(site_item.flow_auto_save_enabled).lower()
        if site_item.web_extraction_enabled is not None:
            site_element.attrib["webExtractionEnabled"] = str(site_item.web_extraction_enabled).lower()
        if site_item.metrics_content_type_enabled is not None:
            site_element.attrib["metricsContentTypeEnabled"] = str(site_item.metrics_content_type_enabled).lower()
        if site_item.notify_site_admins_on_throttle is not None:
            site_element.attrib["notifySiteAdminsOnThrottle"] = str(site_item.notify_site_admins_on_throttle).lower()
        if site_item.authoring_enabled is not None:
            site_element.attrib["authoringEnabled"] = str(site_item.authoring_enabled).lower()
        if site_item.custom_subscription_email_enabled is not None:
            site_element.attrib["customSubscriptionEmailEnabled"] = str(
                site_item.custom_subscription_email_enabled
            ).lower()
        if site_item.custom_subscription_email is not None:
            site_element.attrib["customSubscriptionEmail"] = str(site_item.custom_subscription_email).lower()
        if site_item.custom_subscription_footer_enabled is not None:
            site_element.attrib["customSubscriptionFooterEnabled"] = str(
                site_item.custom_subscription_footer_enabled
            ).lower()
        if site_item.custom_subscription_footer is not None:
            site_element.attrib["customSubscriptionFooter"] = str(site_item.custom_subscription_footer).lower()
        if site_item.ask_data_mode is not None:
            site_element.attrib["askDataMode"] = str(site_item.ask_data_mode)
        if site_item.named_sharing_enabled is not None:
            site_element.attrib["namedSharingEnabled"] = str(site_item.named_sharing_enabled).lower()
        if site_item.mobile_biometrics_enabled is not None:
            site_element.attrib["mobileBiometricsEnabled"] = str(site_item.mobile_biometrics_enabled).lower()
        if site_item.sheet_image_enabled is not None:
            site_element.attrib["sheetImageEnabled"] = str(site_item.sheet_image_enabled).lower()
        if site_item.cataloging_enabled is not None:
            site_element.attrib["catalogingEnabled"] = str(site_item.cataloging_enabled).lower()
        if site_item.derived_permissions_enabled is not None:
            site_element.attrib["derivedPermissionsEnabled"] = str(site_item.derived_permissions_enabled).lower()
        if site_item.user_visibility_mode is not None:
            site_element.attrib["userVisibilityMode"] = str(site_item.user_visibility_mode)
        if site_item.use_default_time_zone is not None:
            site_element.attrib["useDefaultTimeZone"] = str(site_item.use_default_time_zone).lower()
        if site_item.time_zone is not None:
            site_element.attrib["timeZone"] = str(site_item.time_zone)
        if site_item.auto_suspend_refresh_enabled is not None:
            site_element.attrib["autoSuspendRefreshEnabled"] = str(site_item.auto_suspend_refresh_enabled).lower()
        if site_item.auto_suspend_refresh_inactivity_window is not None:
            site_element.attrib["autoSuspendRefreshInactivityWindow"] = str(
                site_item.auto_suspend_refresh_inactivity_window
            )

        return ET.tostring(xml_request)

    def set_versioned_flow_attributes(self, flows_all, flows_edit, flows_schedule, parent_srv, site_element, site_item):
        if (not parent_srv) or SiteItem.use_new_flow_settings(parent_srv):
            if site_item.flows_enabled is not None:
                flows_edit = flows_edit or flows_all
                flows_schedule = flows_schedule or flows_all
                import warnings

                warnings.warn(
                    "FlowsEnabled has been removed and become two options:"
                    " SchedulingFlowsEnabled and EditingFlowsEnabled"
                )
            if site_item.editing_flows_enabled is not None:
                site_element.attrib["editingFlowsEnabled"] = flows_edit
            if site_item.scheduling_flows_enabled is not None:
                site_element.attrib["schedulingFlowsEnabled"] = flows_schedule

        else:
            if site_item.flows_enabled is not None:
                site_element.attrib["flowsEnabled"] = str(site_item.flows_enabled).lower()
            if site_item.editing_flows_enabled is not None or site_item.scheduling_flows_enabled is not None:
                flows_all = flows_all or flows_edit or flows_schedule
                site_element.attrib["flowsEnabled"] = flows_all
                import warnings

                warnings.warn("In version 3.10 and earlier there is only one option: FlowsEnabled")


class TableRequest(object):
    def update_req(self, table_item):
        xml_request = ET.Element("tsRequest")
        table_element = ET.SubElement(xml_request, "table")

        if table_item.contact_id:
            contact_element = ET.SubElement(table_element, "contact")
            contact_element.attrib["id"] = table_item.contact_id

        table_element.attrib["isCertified"] = str(table_item.certified).lower()

        if table_item.certification_note:
            table_element.attrib["certificationNote"] = str(table_item.certification_note)

        if table_item.description:
            table_element.attrib["description"] = str(table_item.description)

        return ET.tostring(xml_request)


class TagRequest(object):
    def add_req(self, tag_set):
        xml_request = ET.Element("tsRequest")
        tags_element = ET.SubElement(xml_request, "tags")
        for tag in tag_set:
            tag_element = ET.SubElement(tags_element, "tag")
            tag_element.attrib["label"] = tag
        return ET.tostring(xml_request)


class UserRequest(object):
    def update_req(self, user_item: UserItem, password: Optional[str]) -> bytes:
        xml_request = ET.Element("tsRequest")
        user_element = ET.SubElement(xml_request, "user")
        if user_item.fullname:
            user_element.attrib["fullName"] = user_item.fullname
        if user_item.email:
            user_element.attrib["email"] = user_item.email
        if user_item.site_role:
            if user_item.site_role != "ServerAdministrator":
                user_element.attrib["siteRole"] = user_item.site_role
        if user_item.auth_setting:
            user_element.attrib["authSetting"] = user_item.auth_setting
        if password:
            user_element.attrib["password"] = password
        return ET.tostring(xml_request)

    def add_req(self, user_item: UserItem) -> bytes:
        xml_request = ET.Element("tsRequest")
        user_element = ET.SubElement(xml_request, "user")
        if isinstance(user_item.name, str):
            user_element.attrib["name"] = user_item.name
        else:
            raise ValueError(f"{user_item} missing name.")
        if isinstance(user_item.site_role, str):
            user_element.attrib["siteRole"] = user_item.site_role
        else:
            raise ValueError(f"{user_item} must have site role populated.")

        if user_item.auth_setting:
            user_element.attrib["authSetting"] = user_item.auth_setting
        return ET.tostring(xml_request)


class WorkbookRequest(object):
    def _generate_xml(
        self,
        workbook_item,
        connection_credentials=None,
        connections=None,
        hidden_views=None,
    ):
        xml_request = ET.Element("tsRequest")
        workbook_element = ET.SubElement(xml_request, "workbook")
        workbook_element.attrib["name"] = workbook_item.name
        if workbook_item.show_tabs:
            workbook_element.attrib["showTabs"] = str(workbook_item.show_tabs).lower()
        project_element = ET.SubElement(workbook_element, "project")
        project_element.attrib["id"] = str(workbook_item.project_id)

        if connection_credentials is not None and connections is not None:
            raise RuntimeError("You cannot set both `connections` and `connection_credentials`")

        if connection_credentials is not None:
            _add_credentials_element(workbook_element, connection_credentials)

        if connections is not None:
            connections_element = ET.SubElement(workbook_element, "connections")
            for connection in connections:
                _add_connections_element(connections_element, connection)

        if hidden_views is not None:
            import warnings

            warnings.simplefilter("always", DeprecationWarning)
            warnings.warn(
                "the hidden_views parameter should now be set on the workbook directly",
                DeprecationWarning,
            )
            if workbook_item.hidden_views is None:
                workbook_item.hidden_views = hidden_views

        if workbook_item.hidden_views is not None:
            views_element = ET.SubElement(workbook_element, "views")
            for view_name in workbook_item.hidden_views:
                _add_hiddenview_element(views_element, view_name)
        return ET.tostring(xml_request)

    def update_req(self, workbook_item):
        xml_request = ET.Element("tsRequest")
        workbook_element = ET.SubElement(xml_request, "workbook")
        if workbook_item.name:
            workbook_element.attrib["name"] = workbook_item.name
        if workbook_item.show_tabs is not None:
            workbook_element.attrib["showTabs"] = str(workbook_item.show_tabs).lower()
        if workbook_item.project_id:
            project_element = ET.SubElement(workbook_element, "project")
            project_element.attrib["id"] = workbook_item.project_id
        if workbook_item.owner_id:
            owner_element = ET.SubElement(workbook_element, "owner")
            owner_element.attrib["id"] = workbook_item.owner_id
        if workbook_item.data_acceleration_config["acceleration_enabled"] is not None:
            data_acceleration_config = workbook_item.data_acceleration_config
            data_acceleration_element = ET.SubElement(workbook_element, "dataAccelerationConfig")
            data_acceleration_element.attrib["accelerationEnabled"] = str(
                data_acceleration_config["acceleration_enabled"]
            ).lower()
            if data_acceleration_config["accelerate_now"] is not None:
                data_acceleration_element.attrib["accelerateNow"] = str(
                    data_acceleration_config["accelerate_now"]
                ).lower()

        return ET.tostring(xml_request)

    def publish_req(
        self,
        workbook_item,
        filename,
        file_contents,
        connection_credentials=None,
        connections=None,
        hidden_views=None,
    ):
        xml_request = self._generate_xml(
            workbook_item,
            connection_credentials=connection_credentials,
            connections=connections,
            hidden_views=hidden_views,
        )

        parts = {
            "request_payload": ("", xml_request, "text/xml"),
            "tableau_workbook": (filename, file_contents, "application/octet-stream"),
        }
        return _add_multipart(parts)

    def publish_req_chunked(
        self,
        workbook_item,
        connection_credentials=None,
        connections=None,
        hidden_views=None,
    ):
        xml_request = self._generate_xml(
            workbook_item,
            connection_credentials=connection_credentials,
            connections=connections,
            hidden_views=hidden_views,
        )

        parts = {"request_payload": ("", xml_request, "text/xml")}
        return _add_multipart(parts)

    @_tsrequest_wrapped
    def embedded_extract_req(self, xml_request, include_all=True, datasources=None):
        list_element = ET.SubElement(xml_request, "datasources")
        if include_all:
            list_element.attrib["includeAll"] = "true"
        elif datasources:
            for datasource_item in datasources:
                datasource_element = ET.SubElement(list_element, "datasource")
                datasource_element.attrib["id"] = datasource_item.id


class Connection(object):
    @_tsrequest_wrapped
    def update_req(self, xml_request: ET.Element, connection_item: "ConnectionItem") -> None:
        connection_element = ET.SubElement(xml_request, "connection")
        if connection_item.server_address is not None:
            connection_element.attrib["serverAddress"] = connection_item.server_address.lower()
        if connection_item.server_port is not None:
            connection_element.attrib["serverPort"] = str(connection_item.server_port)
        if connection_item.username is not None:
            connection_element.attrib["userName"] = connection_item.username
        if connection_item.password is not None:
            connection_element.attrib["password"] = connection_item.password
        if connection_item.embed_password is not None:
            connection_element.attrib["embedPassword"] = str(connection_item.embed_password).lower()


class TaskRequest(object):
    @_tsrequest_wrapped
    def run_req(self, xml_request, task_item):
        # Send an empty tsRequest
        pass


class SubscriptionRequest(object):
    @_tsrequest_wrapped
    def create_req(self, xml_request: ET.Element, subscription_item: "SubscriptionItem") -> bytes:
        subscription_element = ET.SubElement(xml_request, "subscription")

        # Main attributes
        subscription_element.attrib["subject"] = subscription_item.subject
        if subscription_item.attach_image is not None:
            subscription_element.attrib["attachImage"] = str(subscription_item.attach_image).lower()
        if subscription_item.attach_pdf is not None:
            subscription_element.attrib["attachPdf"] = str(subscription_item.attach_pdf).lower()
        if subscription_item.message is not None:
            subscription_element.attrib["message"] = subscription_item.message
        if subscription_item.page_orientation is not None:
            subscription_element.attrib["pageOrientation"] = subscription_item.page_orientation
        if subscription_item.page_size_option is not None:
            subscription_element.attrib["pageSizeOption"] = subscription_item.page_size_option

        # Content element
        content_element = ET.SubElement(subscription_element, "content")
        content_element.attrib["id"] = subscription_item.target.id
        content_element.attrib["type"] = subscription_item.target.type
        if subscription_item.send_if_view_empty is not None:
            content_element.attrib["sendIfViewEmpty"] = str(subscription_item.send_if_view_empty).lower()

        # Schedule element
        schedule_element = ET.SubElement(subscription_element, "schedule")
        schedule_element.attrib["id"] = subscription_item.schedule_id

        # User element
        user_element = ET.SubElement(subscription_element, "user")
        user_element.attrib["id"] = subscription_item.user_id
        return ET.tostring(xml_request)

    @_tsrequest_wrapped
    def update_req(self, xml_request: ET.Element, subscription_item: "SubscriptionItem") -> bytes:
        subscription = ET.SubElement(xml_request, "subscription")

        # Main attributes
        if subscription_item.subject is not None:
            subscription.attrib["subject"] = subscription_item.subject
        if subscription_item.attach_image is not None:
            subscription.attrib["attachImage"] = str(subscription_item.attach_image).lower()
        if subscription_item.attach_pdf is not None:
            subscription.attrib["attachPdf"] = str(subscription_item.attach_pdf).lower()
        if subscription_item.page_orientation is not None:
            subscription.attrib["pageOrientation"] = subscription_item.page_orientation
        if subscription_item.page_size_option is not None:
            subscription.attrib["pageSizeOption"] = subscription_item.page_size_option
        if subscription_item.suspended is not None:
            subscription.attrib["suspended"] = str(subscription_item.suspended).lower()

        # Schedule element
        schedule = ET.SubElement(subscription, "schedule")
        if subscription_item.schedule_id is not None:
            schedule.attrib["id"] = subscription_item.schedule_id

        # Content element
        content = ET.SubElement(subscription, "content")
        if subscription_item.send_if_view_empty is not None:
            content.attrib["sendIfViewEmpty"] = str(subscription_item.send_if_view_empty).lower()
        return ET.tostring(xml_request)


class EmptyRequest(object):
    @_tsrequest_wrapped
    def empty_req(self, xml_request):
        pass


class WebhookRequest(object):
    @_tsrequest_wrapped
    def create_req(self, xml_request: ET.Element, webhook_item: "WebhookItem") -> bytes:
        webhook = ET.SubElement(xml_request, "webhook")
        if isinstance(webhook_item.name, str):
            webhook.attrib["name"] = webhook_item.name
        else:
            raise ValueError(f"Name must be provided for {webhook_item}")

        source = ET.SubElement(webhook, "webhook-source")
        if isinstance(webhook_item._event, str):
            ET.SubElement(source, webhook_item._event)
        else:
            raise ValueError(f"_event for Webhook must be provided. {webhook_item}")

        destination = ET.SubElement(webhook, "webhook-destination")
        post = ET.SubElement(destination, "webhook-destination-http")
        post.attrib["method"] = "POST"
        if isinstance(webhook_item.url, str):
            post.attrib["url"] = webhook_item.url
        else:
            raise ValueError(f"URL must be provided on {webhook_item}")

        return ET.tostring(xml_request)


class MetricRequest:
    @_tsrequest_wrapped
    def update_req(self, xml_request: ET.Element, metric_item: MetricItem) -> bytes:
        metric_element = ET.SubElement(xml_request, "metric")
        if metric_item.id is not None:
            metric_element.attrib["id"] = metric_item.id
        if metric_item.name is not None:
            metric_element.attrib["name"] = metric_item.name
        if metric_item.description is not None:
            metric_element.attrib["description"] = metric_item.description
        if metric_item.suspended is not None:
            metric_element.attrib["suspended"] = str(metric_item.suspended).lower()
        if metric_item.project_id is not None:
            ET.SubElement(metric_element, "project", {"id": metric_item.project_id})
        if metric_item.owner_id is not None:
            ET.SubElement(metric_element, "owner", {"id": metric_item.owner_id})

        return ET.tostring(xml_request)


class RequestFactory(object):
    Auth = AuthRequest()
    Connection = Connection()
    Column = ColumnRequest()
    DataAlert = DataAlertRequest()
    Datasource = DatasourceRequest()
    Database = DatabaseRequest()
    DQW = DQWRequest()
    Empty = EmptyRequest()
    Favorite = FavoriteRequest()
    Fileupload = FileuploadRequest()
    Flow = FlowRequest()
    Group = GroupRequest()
    Metric = MetricRequest()
    Permission = PermissionRequest()
    Project = ProjectRequest()
    Schedule = ScheduleRequest()
    Site = SiteRequest()
    Subscription = SubscriptionRequest()
    Table = TableRequest()
    Tag = TagRequest()
    Task = TaskRequest()
    User = UserRequest()
    Workbook = WorkbookRequest()
    Webhook = WebhookRequest()
