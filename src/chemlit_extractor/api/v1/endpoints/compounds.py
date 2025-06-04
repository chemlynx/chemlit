"""API endpoints for compound operations."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from chemlit_extractor.database import CompoundCRUD, CompoundPropertyCRUD, get_db
from chemlit_extractor.models.schemas import (
    Compound,
    CompoundCreate,
    CompoundProperty,
    CompoundPropertyCreate,
    CompoundPropertyUpdate,
    CompoundUpdate,
)

router = APIRouter()


@router.get("/", response_model=list[Compound])
def get_compounds(
    skip: int = Query(0, ge=0, description="Number of compounds to skip"),
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum number of compounds to return"
    ),
    db: Session = Depends(get_db),
) -> list[Compound]:
    """
    Get compounds with pagination.

    Args:
        skip: Number of compounds to skip.
        limit: Maximum number of compounds to return.

    Returns:
        List of compounds with their properties.
    """
    return CompoundCRUD.get_multi(db, skip=skip, limit=limit)


@router.get("/{compound_id}", response_model=Compound)
def get_compound(
    compound_id: int,
    db: Session = Depends(get_db),
) -> Compound:
    """
    Get a specific compound by ID.

    Args:
        compound_id: ID of the compound to retrieve.

    Returns:
        Compound details including associated properties.

    Raises:
        404: If compound with the given ID is not found.
    """
    compound = CompoundCRUD.get_by_id(db, compound_id)
    if not compound:
        raise HTTPException(
            status_code=404, detail=f"Compound with ID {compound_id} not found"
        )
    return compound


@router.post("/", response_model=Compound, status_code=201)
def create_compound(
    compound: CompoundCreate,
    db: Session = Depends(get_db),
) -> Compound:
    """
    Create a new compound.

    Args:
        compound: Compound data to create.

    Returns:
        Created compound with assigned ID and timestamps.

    Raises:
        400: If referenced article doesn't exist.
    """
    try:
        return CompoundCRUD.create(db, compound)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{compound_id}", response_model=Compound)
def update_compound(
    compound_id: int,
    compound_update: CompoundUpdate,
    db: Session = Depends(get_db),
) -> Compound:
    """
    Update an existing compound.

    Args:
        compound_id: ID of the compound to update.
        compound_update: Updated compound data.

    Returns:
        Updated compound.

    Raises:
        404: If compound with the given ID is not found.
    """
    updated_compound = CompoundCRUD.update(db, compound_id, compound_update)
    if not updated_compound:
        raise HTTPException(
            status_code=404, detail=f"Compound with ID {compound_id} not found"
        )
    return updated_compound


@router.delete("/{compound_id}", status_code=204)
def delete_compound(
    compound_id: int,
    db: Session = Depends(get_db),
) -> None:
    """
    Delete a compound and all associated properties.

    This will cascade delete all properties of the compound.

    Args:
        compound_id: ID of the compound to delete.

    Raises:
        404: If compound with the given ID is not found.
    """
    success = CompoundCRUD.delete(db, compound_id)
    if not success:
        raise HTTPException(
            status_code=404, detail=f"Compound with ID {compound_id} not found"
        )


@router.get("/{compound_id}/properties", response_model=list[CompoundProperty])
def get_compound_properties(
    compound_id: int,
    db: Session = Depends(get_db),
) -> list[CompoundProperty]:
    """
    Get all properties for a specific compound.

    Args:
        compound_id: ID of the compound.

    Returns:
        List of properties associated with the compound.

    Raises:
        404: If compound with the given ID is not found.
    """
    # First check if compound exists
    compound = CompoundCRUD.get_by_id(db, compound_id)
    if not compound:
        raise HTTPException(
            status_code=404, detail=f"Compound with ID {compound_id} not found"
        )

    return CompoundPropertyCRUD.get_by_compound(db, compound_id)


@router.post(
    "/{compound_id}/properties", response_model=CompoundProperty, status_code=201
)
def create_compound_property(
    compound_id: int,
    property_data: CompoundPropertyCreate,
    db: Session = Depends(get_db),
) -> CompoundProperty:
    """
    Create a new property for a compound.

    Args:
        compound_id: ID of the compound (must match property_data.compound_id).
        property_data: Property data to create.

    Returns:
        Created property with assigned ID and timestamps.

    Raises:
        400: If compound_id mismatch or compound doesn't exist.
    """
    # Validate compound_id matches
    if property_data.compound_id != compound_id:
        raise HTTPException(
            status_code=400,
            detail="Compound ID in URL must match compound_id in request body",
        )

    try:
        return CompoundPropertyCRUD.create(db, property_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/properties/{property_id}", response_model=CompoundProperty)
def update_compound_property(
    property_id: int,
    property_update: CompoundPropertyUpdate,
    db: Session = Depends(get_db),
) -> CompoundProperty:
    """
    Update an existing compound property.

    Args:
        property_id: ID of the property to update.
        property_update: Updated property data.

    Returns:
        Updated property.

    Raises:
        404: If property with the given ID is not found.
    """
    updated_property = CompoundPropertyCRUD.update(db, property_id, property_update)
    if not updated_property:
        raise HTTPException(
            status_code=404, detail=f"Property with ID {property_id} not found"
        )
    return updated_property


@router.delete("/properties/{property_id}", status_code=204)
def delete_compound_property(
    property_id: int,
    db: Session = Depends(get_db),
) -> None:
    """
    Delete a compound property.

    Args:
        property_id: ID of the property to delete.

    Raises:
        404: If property with the given ID is not found.
    """
    success = CompoundPropertyCRUD.delete(db, property_id)
    if not success:
        raise HTTPException(
            status_code=404, detail=f"Property with ID {property_id} not found"
        )
