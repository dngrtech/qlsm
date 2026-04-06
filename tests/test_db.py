import pytest
from ui.models import QLInstance, Host, HostStatus, InstanceStatus, ConfigPreset # Import InstanceStatus, ConfigPreset
from ui.database import (
    get_instances, get_instance, get_instance_by_name,
    create_instance, update_instance, delete_instance,
    create_host, # Import create_host
    # Import preset helpers
    get_presets, get_preset, get_preset_by_name,
    create_preset, update_preset, delete_preset
)

def test_create_instance(app_context):
    """Test creating a new QL instance."""
    # Create a dummy host first
    dummy_host = create_host(name='dummy-host-create', provider='vultr', region='dummy-reg', machine_size='dummy-size', status=HostStatus.ACTIVE)
    assert dummy_host is not None

    instance = create_instance(
        name='Test Instance',
        host_id=dummy_host.id, # Use host_id
        port=27960,
        hostname='Test Instance Server',
        config='{"test": "config"}'
    )
    
    assert instance.id is not None
    assert instance.name == 'Test Instance'
    # assert instance.host == 'test-host.example.com' # This assertion is no longer valid
    assert instance.host_id == dummy_host.id # Assert host_id
    assert instance.port == 27960
    assert instance.config == '{"test": "config"}'
    assert instance.status == InstanceStatus.IDLE # Compare with Enum member

def test_get_instance(app_context):
    """Test retrieving a QL instance by ID."""
    # Create a dummy host first
    dummy_host = create_host(name='dummy-host-get', provider='vultr', region='dummy-reg', machine_size='dummy-size', status=HostStatus.ACTIVE)
    assert dummy_host is not None

    # Create a test instance
    instance = create_instance(
        name='Test Get Instance',
        host_id=dummy_host.id, # Use host_id
        port=27961,
        hostname='Test Get Instance Server'
    )
    
    # Retrieve the instance
    retrieved = get_instance(instance.id)
    
    assert retrieved is not None
    assert retrieved.id == instance.id
    assert retrieved.name == 'Test Get Instance'
    assert retrieved.host_id == dummy_host.id # Assert host_id

    # Test getting a non-existent instance
    non_existent_instance = get_instance(999)
    assert non_existent_instance is None

def test_get_instance_by_name(app_context):
    """Test retrieving a QL instance by name."""
    # Create a dummy host first
    dummy_host = create_host(name='dummy-host-get-by-name', provider='vultr', region='dummy-reg', machine_size='dummy-size', status=HostStatus.ACTIVE)
    assert dummy_host is not None

    # Create a test instance
    instance = create_instance(
        name='Test Get By Name',
        host_id=dummy_host.id, # Use host_id
        port=27962,
        hostname='Test Get By Name Server'
    )
    
    # Retrieve the instance
    retrieved = get_instance_by_name('Test Get By Name')
    
    assert retrieved is not None
    assert retrieved.id == instance.id
    assert retrieved.name == 'Test Get By Name'
    assert retrieved.host_id == dummy_host.id # Assert host_id

    # Test getting a non-existent instance by name
    non_existent_instance = get_instance_by_name('Non Existent')
    assert non_existent_instance is None

def test_get_instances(app_context):
    """Test retrieving all QL instances."""
    # Create dummy hosts first
    dummy_host_1 = create_host(name='dummy-host-get-instances-1', provider='vultr', region='dummy-reg-1', machine_size='dummy-size-1', status=HostStatus.ACTIVE)
    dummy_host_2 = create_host(name='dummy-host-get-instances-2', provider='gcp', region='dummy-reg-2', machine_size='dummy-size-2', status=HostStatus.ACTIVE)
    assert dummy_host_1 is not None
    assert dummy_host_2 is not None

    # Create test instances
    create_instance(name='Test Instance 1', host_id=dummy_host_1.id, port=27960, hostname='Test Instance 1 Server') # Use host_id
    create_instance(name='Test Instance 2', host_id=dummy_host_2.id, port=27961, hostname='Test Instance 2 Server') # Use host_id
    
    # Retrieve all instances
    instances = get_instances()
    
    assert len(instances) >= 2
    assert any(i.name == 'Test Instance 1' for i in instances)
    assert any(i.name == 'Test Instance 2' for i in instances)
    # Optional: Assert host_ids are correctly set
    assert any(i.name == 'Test Instance 1' and i.host_id == dummy_host_1.id for i in instances)
    assert any(i.name == 'Test Instance 2' and i.host_id == dummy_host_2.id for i in instances)


def test_update_instance(app_context):
    """Test updating a QL instance."""
    # Create dummy hosts first
    old_host = create_host(name='old-host-update', provider='vultr', region='old-reg', machine_size='old-size', status=HostStatus.ACTIVE)
    new_host = create_host(name='new-host-update', provider='vultr', region='new-reg', machine_size='new-size', status=HostStatus.ACTIVE)
    assert old_host is not None
    assert new_host is not None

    # Create a test instance
    instance = create_instance(
        name='Test Update Instance',
        host_id=old_host.id, # Use host_id
        port=27963,
        hostname='Test Update Instance Server'
    )
    
    # Update the instance
    updated = update_instance(
        instance.id,
        # host='new-host.example.com', # Update with host_id
        host_id=new_host.id,
        port=27964,
        status=InstanceStatus.RUNNING # Pass Enum member
    )
    
    assert updated is not None
    assert updated.id == instance.id
    assert updated.name == 'Test Update Instance'  # Name unchanged
    # assert updated.host == 'new-host.example.com'  # Host updated - assertion needs update
    assert updated.host_id == new_host.id # Assert host_id updated
    assert updated.port == 27964  # Port updated
    assert updated.status == InstanceStatus.RUNNING  # Status updated (compare with Enum)

    # Verify changes in the database
    retrieved_instance = get_instance(instance.id) # Use instance.id instead of original_id
    assert retrieved_instance is not None
    # The name wasn't updated in the update_instance call, so assert the original name
    assert retrieved_instance.name == 'Test Update Instance'
    # assert retrieved_instance.host == 'new-host.example.com' # Assertion needs update
    assert retrieved_instance.host_id == new_host.id # Assert host_id updated
    assert retrieved_instance.port == 27964
    # config was not updated in this test, should remain original
    assert retrieved_instance.config is None # Assuming original config was None
    assert retrieved_instance.status == InstanceStatus.RUNNING # Assert status updated (compare with Enum)

    # Test updating a non-existent instance
    non_existent_update = update_instance(999, name='Should Not Exist')
    assert non_existent_update is None

def test_delete_instance(app_context):
    """Test deleting a QL instance."""
    # Create a dummy host first
    dummy_host = create_host(name='dummy-host-delete-db', provider='vultr', region='dummy-reg', machine_size='dummy-size', status=HostStatus.ACTIVE)
    assert dummy_host is not None

    # Create a test instance
    instance = create_instance(
        name='Test Delete Instance',
        host_id=dummy_host.id, # Use host_id
        port=27965,
        hostname='Test Delete Instance Server'
    )
    
    # Delete the instance
    result = delete_instance(instance.id)
    
    assert result is True
    
    # Verify the instance is deleted
    deleted = get_instance(instance.id)
    assert deleted is None


# --- Config Preset Tests ---
# Note: Presets now use filesystem-based storage. The model stores metadata (name, description, path)
# while config content is stored on disk at the path location.

def test_create_preset(app_context):
    """Test creating a new ConfigPreset with filesystem-based storage."""
    preset = create_preset(
        name='Test Preset Create',
        description='A test preset',
        path='configs/presets/test-preset-create'
    )
    assert preset.id is not None
    assert preset.name == 'Test Preset Create'
    assert preset.description == 'A test preset'
    assert preset.path == 'configs/presets/test-preset-create'

def test_get_preset(app_context):
    """Test retrieving a ConfigPreset by ID."""
    preset = create_preset(name='Test Preset Get', path='configs/presets/test-preset-get')
    retrieved = get_preset(preset.id)
    assert retrieved is not None
    assert retrieved.id == preset.id
    assert retrieved.name == 'Test Preset Get'

    non_existent = get_preset(999)
    assert non_existent is None

def test_get_preset_by_name(app_context):
    """Test retrieving a ConfigPreset by name."""
    preset = create_preset(name='Test Preset Get By Name', path='configs/presets/test-preset-get-by-name')
    retrieved = get_preset_by_name('Test Preset Get By Name')
    assert retrieved is not None
    assert retrieved.id == preset.id
    assert retrieved.name == 'Test Preset Get By Name'

    non_existent = get_preset_by_name('Non Existent Preset')
    assert non_existent is None

def test_get_presets(app_context):
    """Test retrieving all ConfigPresets."""
    create_preset(name='Preset A', path='configs/presets/preset-a')
    create_preset(name='Preset B', path='configs/presets/preset-b')
    presets = get_presets()
    assert len(presets) >= 2
    assert any(p.name == 'Preset A' for p in presets)
    assert any(p.name == 'Preset B' for p in presets)

def test_update_preset(app_context):
    """Test updating a ConfigPreset."""
    preset = create_preset(
        name='Test Preset Update Old',
        description='Old Desc',
        path='configs/presets/test-preset-update-old'
    )
    original_id = preset.id

    updated = update_preset(
        original_id,
        name='Test Preset Update New',
        description='New Desc',
        path='configs/presets/test-preset-update-new'
    )

    assert updated is not None
    assert updated.id == original_id
    assert updated.name == 'Test Preset Update New'
    assert updated.description == 'New Desc'
    assert updated.path == 'configs/presets/test-preset-update-new'

    # Verify in DB
    retrieved = get_preset(original_id)
    assert retrieved.name == 'Test Preset Update New'
    assert retrieved.description == 'New Desc'
    assert retrieved.path == 'configs/presets/test-preset-update-new'

    non_existent = update_preset(999, name='Should Fail')
    assert non_existent is None

def test_delete_preset(app_context):
    """Test deleting a ConfigPreset."""
    preset = create_preset(name='Test Preset Delete', path='configs/presets/test-preset-delete')
    preset_id = preset.id
    result = delete_preset(preset_id)
    assert result is True

    deleted = get_preset(preset_id)
    assert deleted is None
