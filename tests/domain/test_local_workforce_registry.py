"""Tests for the Local Workforce Registry."""

import json
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from aios.core.llm import OllamaClient
from aios.domain.local_workforce.registry import LocalWorkforceRegistry
from aios.domain.local_workforce.contracts import LocalWorkerModel, LocalJobProfile
from aios.memory.db import get_connection, init_memory_db


@pytest.fixture
def memory_db():
    """Ensure a fresh memory DB schema for these tests."""
    init_memory_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM local_worker_models")
        conn.commit()


@pytest.fixture
def fake_ollama():
    """Mock Ollama client returning detailed model listings."""
    client = MagicMock(spec=OllamaClient)
    client.list_detailed_models.return_value = [
        {
            "name": "llama3.2:3b",
            "details": {
                "family": "llama",
                "parameter_size": "3B",
                "quantization_level": "Q4_K_M"
            }
        },
        {
            "name": "qwen2.5:3b",
            "details": {
                "family": "qwen",
                "parameter_size": "3B",
                "quantization_level": "Q4_K_M"
            }
        }
    ]
    return client


def test_registry_reconciliation_discovery(memory_db, fake_ollama):
    """Test that reconcile() discovers and inserts new models."""
    registry = LocalWorkforceRegistry(fake_ollama)
    
    # Initially empty
    assert len(registry.list_models()) == 0
    
    # Reconcile should discover the two models
    registry.reconcile()
    
    models = registry.list_models()
    assert len(models) == 2
    
    # Verify defaults
    llama = registry.get_model("llama3.2:3b")
    assert llama is not None
    assert llama.installed is True
    assert llama.operator_approved is False
    assert llama.health == "unknown"
    assert len(llama.allowed_job_profiles) == 0
    assert llama.family == "llama"
    assert llama.metadata_confidence == "verified"


def test_registry_reconciliation_uninstalls(memory_db, fake_ollama):
    """Test that models no longer reported by Ollama are marked uninstalled but not deleted."""
    registry = LocalWorkforceRegistry(fake_ollama)
    registry.reconcile()
    
    # Now simulate qwen being deleted from Ollama
    fake_ollama.list_detailed_models.return_value = [
        {
            "name": "llama3.2:3b",
            "details": {
                "family": "llama",
                "parameter_size": "3B",
                "quantization_level": "Q4_K_M"
            }
        }
    ]
    
    registry.reconcile()
    
    models = registry.list_models()
    assert len(models) == 2  # qwen should still be in the DB
    
    llama = registry.get_model("llama3.2:3b")
    qwen = registry.get_model("qwen2.5:3b")
    
    assert llama.installed is True
    assert qwen.installed is False


def test_registry_preserves_configuration_across_restarts(memory_db, fake_ollama):
    """Enforce the gate: configuration remains identical after backend restart."""
    # Instance 1: Discovery and manual configuration
    registry1 = LocalWorkforceRegistry(fake_ollama)
    registry1.reconcile()
    
    registry1.update_approval("llama3.2:3b", True)
    registry1.update_admission("llama3.2:3b", "approved", "Approved for general clerical work")
    registry1.update_profiles("llama3.2:3b", {LocalJobProfile.CLASSIFY, LocalJobProfile.SUMMARISE})
    registry1.record_health("llama3.2:3b", "healthy", success=True)
    
    # "Restart": Instance 2 should load identical state
    registry2 = LocalWorkforceRegistry(fake_ollama)
    # The models list should already contain the state without reconciling
    models = registry2.list_models()
    assert len(models) == 2
    
    llama = registry2.get_model("llama3.2:3b")
    assert llama.operator_approved is True
    assert llama.admission_status == "approved"
    assert llama.admission_reason == "Approved for general clerical work"
    assert llama.health == "healthy"
    assert llama.last_success is not None
    assert LocalJobProfile.CLASSIFY in llama.allowed_job_profiles
    assert LocalJobProfile.SUMMARISE in llama.allowed_job_profiles


def test_registry_records_failure_count(memory_db, fake_ollama):
    """Ensure failures increment the failure count."""
    registry = LocalWorkforceRegistry(fake_ollama)
    registry.reconcile()
    
    registry.record_health("llama3.2:3b", "failing", success=False)
    registry.record_health("llama3.2:3b", "failing", success=False)
    
    llama = registry.get_model("llama3.2:3b")
    assert llama.health == "failing"
    assert llama.failure_count == 2
