"""CRUD operations for database models."""


from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, selectinload

from chemlit_extractor.database.models import (
    Article,
    Author,
    Compound,
    CompoundProperty,
)
from chemlit_extractor.models.schemas import (
    ArticleCreate,
    ArticleSearchQuery,
    ArticleUpdate,
    AuthorCreate,
    AuthorUpdate,
    CompoundCreate,
    CompoundPropertyCreate,
    CompoundPropertyUpdate,
    CompoundUpdate,
    DatabaseStats,
)


class ArticleCRUD:
    """CRUD operations for Article model."""

    @staticmethod
    def create(
        db: Session, article: ArticleCreate, authors: list[AuthorCreate] | None = None
    ) -> Article:
        """
        Create a new article with optional authors.

        Args:
            db: Database session.
            article: Article data to create.
            authors: Optional list of authors to associate.

        Returns:
            Created article instance.

        Raises:
            ValueError: If article with DOI already exists.
        """
        # Check if article already exists
        existing = ArticleCRUD.get_by_doi(db, article.doi)
        if existing:
            raise ValueError(f"Article with DOI {article.doi} already exists")

        db_article = Article(**article.model_dump())

        # Add authors if provided
        if authors:
            for author_data in authors:
                # Try to find existing author or create new one
                author = AuthorCRUD.get_or_create(db, author_data)
                db_article.authors.append(author)

        db.add(db_article)
        db.commit()
        db.refresh(db_article)
        return db_article

    @staticmethod
    def get_by_doi(db: Session, doi: str) -> Article | None:
        """
        Get article by DOI.

        Args:
            db: Database session.
            doi: Article DOI.

        Returns:
            Article instance or None if not found.
        """
        return (
            db.query(Article)
            .options(selectinload(Article.authors))
            .filter(Article.doi == doi.lower())
            .first()
        )

    @staticmethod
    def get_multi(db: Session, skip: int = 0, limit: int = 100) -> list[Article]:
        """
        Get multiple articles with pagination.

        Args:
            db: Database session.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of article instances.
        """
        return (
            db.query(Article)
            .options(selectinload(Article.authors))
            .order_by(Article.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    @staticmethod
    def search(db: Session, query: ArticleSearchQuery) -> tuple[list[Article], int]:
        """
        Search articles based on query parameters.

        Args:
            db: Database session.
            query: Search query parameters.

        Returns:
            Tuple of (articles, total_count).
        """
        base_query = db.query(Article).options(selectinload(Article.authors))

        # Build filters
        filters = []

        if query.doi:
            filters.append(Article.doi.ilike(f"%{query.doi.lower()}%"))

        if query.title:
            filters.append(Article.title.ilike(f"%{query.title}%"))

        if query.journal:
            filters.append(Article.journal.ilike(f"%{query.journal}%"))

        if query.year:
            filters.append(Article.year == query.year)

        if query.author:
            # Search in authors' names
            author_filter = or_(
                Author.first_name.ilike(f"%{query.author}%"),
                Author.last_name.ilike(f"%{query.author}%"),
            )
            base_query = base_query.join(Article.authors).filter(author_filter)

        # Apply filters
        if filters:
            base_query = base_query.filter(and_(*filters))

        # Get total count before pagination
        total_count = base_query.count()

        # Apply pagination and ordering
        articles = (
            base_query.order_by(Article.created_at.desc())
            .offset(query.offset)
            .limit(query.limit)
            .all()
        )

        return articles, total_count

    @staticmethod
    def update(db: Session, doi: str, article_update: ArticleUpdate) -> Article | None:
        """
        Update an article.

        Args:
            db: Database session.
            doi: Article DOI.
            article_update: Updated article data.

        Returns:
            Updated article instance or None if not found.
        """
        db_article = ArticleCRUD.get_by_doi(db, doi)
        if not db_article:
            return None

        update_data = article_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_article, field, value)

        db.commit()
        db.refresh(db_article)
        return db_article

    @staticmethod
    def delete(db: Session, doi: str) -> bool:
        """
        Delete an article.

        Args:
            db: Database session.
            doi: Article DOI.

        Returns:
            True if deleted, False if not found.
        """
        db_article = ArticleCRUD.get_by_doi(db, doi)
        if not db_article:
            return False

        db.delete(db_article)
        db.commit()
        return True

    @staticmethod
    def count(db: Session) -> int:
        """
        Get total count of articles.

        Args:
            db: Database session.

        Returns:
            Total number of articles.
        """
        return db.query(Article).count()


class AuthorCRUD:
    """CRUD operations for Author model."""

    @staticmethod
    def create(db: Session, author: AuthorCreate) -> Author:
        """
        Create a new author.

        Args:
            db: Database session.
            author: Author data to create.

        Returns:
            Created author instance.
        """
        db_author = Author(**author.model_dump())
        db.add(db_author)
        db.commit()
        db.refresh(db_author)
        return db_author

    @staticmethod
    def get_or_create(db: Session, author: AuthorCreate) -> Author:
        """
        Get existing author or create new one.

        Args:
            db: Database session.
            author: Author data.

        Returns:
            Author instance (existing or newly created).
        """
        # Try to find by ORCID first (if provided)
        if author.orcid:
            db_author = db.query(Author).filter(Author.orcid == author.orcid).first()
            if db_author:
                return db_author

        # Try to find by name
        db_author = (
            db.query(Author)
            .filter(
                and_(
                    Author.first_name == author.first_name,
                    Author.last_name == author.last_name,
                )
            )
            .first()
        )

        if db_author:
            return db_author

        # Create new author
        return AuthorCRUD.create(db, author)

    @staticmethod
    def get_by_id(db: Session, author_id: int) -> Author | None:
        """
        Get author by ID.

        Args:
            db: Database session.
            author_id: Author ID.

        Returns:
            Author instance or None if not found.
        """
        return db.query(Author).filter(Author.id == author_id).first()

    @staticmethod
    def get_multi(db: Session, skip: int = 0, limit: int = 100) -> list[Author]:
        """
        Get multiple authors with pagination.

        Args:
            db: Database session.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of author instances.
        """
        return (
            db.query(Author)
            .order_by(Author.last_name, Author.first_name)
            .offset(skip)
            .limit(limit)
            .all()
        )

    @staticmethod
    def update(
        db: Session, author_id: int, author_update: AuthorUpdate
    ) -> Author | None:
        """
        Update an author.

        Args:
            db: Database session.
            author_id: Author ID.
            author_update: Updated author data.

        Returns:
            Updated author instance or None if not found.
        """
        db_author = AuthorCRUD.get_by_id(db, author_id)
        if not db_author:
            return None

        update_data = author_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_author, field, value)

        db.commit()
        db.refresh(db_author)
        return db_author

    @staticmethod
    def delete(db: Session, author_id: int) -> bool:
        """
        Delete an author.

        Args:
            db: Database session.
            author_id: Author ID.

        Returns:
            True if deleted, False if not found.
        """
        db_author = AuthorCRUD.get_by_id(db, author_id)
        if not db_author:
            return False

        db.delete(db_author)
        db.commit()
        return True

    @staticmethod
    def count(db: Session) -> int:
        """
        Get total count of authors.

        Args:
            db: Database session.

        Returns:
            Total number of authors.
        """
        return db.query(Author).count()


class CompoundCRUD:
    """CRUD operations for Compound model."""

    @staticmethod
    def create(db: Session, compound: CompoundCreate) -> Compound:
        """
        Create a new compound.

        Args:
            db: Database session.
            compound: Compound data to create.

        Returns:
            Created compound instance.

        Raises:
            ValueError: If referenced article doesn't exist.
        """
        # Verify article exists
        article = ArticleCRUD.get_by_doi(db, compound.article_doi)
        if not article:
            raise ValueError(f"Article with DOI {compound.article_doi} not found")

        db_compound = Compound(**compound.model_dump())
        db.add(db_compound)
        db.commit()
        db.refresh(db_compound)
        return db_compound

    @staticmethod
    def get_by_id(db: Session, compound_id: int) -> Compound | None:
        """
        Get compound by ID.

        Args:
            db: Database session.
            compound_id: Compound ID.

        Returns:
            Compound instance or None if not found.
        """
        return (
            db.query(Compound)
            .options(selectinload(Compound.properties))
            .filter(Compound.id == compound_id)
            .first()
        )

    @staticmethod
    def get_by_article(db: Session, article_doi: str) -> list[Compound]:
        """
        Get all compounds for an article.

        Args:
            db: Database session.
            article_doi: Article DOI.

        Returns:
            List of compound instances.
        """
        return (
            db.query(Compound)
            .options(selectinload(Compound.properties))
            .filter(Compound.article_doi == article_doi.lower())
            .order_by(Compound.created_at)
            .all()
        )

    @staticmethod
    def get_multi(db: Session, skip: int = 0, limit: int = 100) -> list[Compound]:
        """
        Get multiple compounds with pagination.

        Args:
            db: Database session.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of compound instances.
        """
        return (
            db.query(Compound)
            .options(selectinload(Compound.properties))
            .order_by(Compound.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    @staticmethod
    def update(
        db: Session, compound_id: int, compound_update: CompoundUpdate
    ) -> Compound | None:
        """
        Update a compound.

        Args:
            db: Database session.
            compound_id: Compound ID.
            compound_update: Updated compound data.

        Returns:
            Updated compound instance or None if not found.
        """
        db_compound = CompoundCRUD.get_by_id(db, compound_id)
        if not db_compound:
            return None

        update_data = compound_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_compound, field, value)

        db.commit()
        db.refresh(db_compound)
        return db_compound

    @staticmethod
    def delete(db: Session, compound_id: int) -> bool:
        """
        Delete a compound.

        Args:
            db: Database session.
            compound_id: Compound ID.

        Returns:
            True if deleted, False if not found.
        """
        db_compound = CompoundCRUD.get_by_id(db, compound_id)
        if not db_compound:
            return False

        db.delete(db_compound)
        db.commit()
        return True

    @staticmethod
    def count(db: Session) -> int:
        """
        Get total count of compounds.

        Args:
            db: Database session.

        Returns:
            Total number of compounds.
        """
        return db.query(Compound).count()


class CompoundPropertyCRUD:
    """CRUD operations for CompoundProperty model."""

    @staticmethod
    def create(db: Session, property_data: CompoundPropertyCreate) -> CompoundProperty:
        """
        Create a new compound property.

        Args:
            db: Database session.
            property_data: Property data to create.

        Returns:
            Created property instance.

        Raises:
            ValueError: If referenced compound doesn't exist.
        """
        # Verify compound exists
        compound = CompoundCRUD.get_by_id(db, property_data.compound_id)
        if not compound:
            raise ValueError(f"Compound with ID {property_data.compound_id} not found")

        db_property = CompoundProperty(**property_data.model_dump())
        db.add(db_property)
        db.commit()
        db.refresh(db_property)
        return db_property

    @staticmethod
    def get_by_id(db: Session, property_id: int) -> CompoundProperty | None:
        """
        Get property by ID.

        Args:
            db: Database session.
            property_id: Property ID.

        Returns:
            Property instance or None if not found.
        """
        return (
            db.query(CompoundProperty)
            .filter(CompoundProperty.id == property_id)
            .first()
        )

    @staticmethod
    def get_by_compound(db: Session, compound_id: int) -> list[CompoundProperty]:
        """
        Get all properties for a compound.

        Args:
            db: Database session.
            compound_id: Compound ID.

        Returns:
            List of property instances.
        """
        return (
            db.query(CompoundProperty)
            .filter(CompoundProperty.compound_id == compound_id)
            .order_by(CompoundProperty.property_name)
            .all()
        )

    @staticmethod
    def get_multi(
        db: Session, skip: int = 0, limit: int = 100
    ) -> list[CompoundProperty]:
        """
        Get multiple properties with pagination.

        Args:
            db: Database session.
            skip: Number of records to skip.
            limit: Maximum number of records to return.

        Returns:
            List of property instances.
        """
        return (
            db.query(CompoundProperty)
            .order_by(CompoundProperty.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    @staticmethod
    def update(
        db: Session, property_id: int, property_update: CompoundPropertyUpdate
    ) -> CompoundProperty | None:
        """
        Update a compound property.

        Args:
            db: Database session.
            property_id: Property ID.
            property_update: Updated property data.

        Returns:
            Updated property instance or None if not found.
        """
        db_property = CompoundPropertyCRUD.get_by_id(db, property_id)
        if not db_property:
            return None

        update_data = property_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_property, field, value)

        db.commit()
        db.refresh(db_property)
        return db_property

    @staticmethod
    def delete(db: Session, property_id: int) -> bool:
        """
        Delete a compound property.

        Args:
            db: Database session.
            property_id: Property ID.

        Returns:
            True if deleted, False if not found.
        """
        db_property = CompoundPropertyCRUD.get_by_id(db, property_id)
        if not db_property:
            return False

        db.delete(db_property)
        db.commit()
        return True

    @staticmethod
    def count(db: Session) -> int:
        """
        Get total count of compound properties.

        Args:
            db: Database session.

        Returns:
            Total number of properties.
        """
        return db.query(CompoundProperty).count()


def get_database_stats(db: Session) -> DatabaseStats:
    """
    Get database statistics.

    Args:
        db: Database session.

    Returns:
        Database statistics.
    """
    return DatabaseStats(
        total_articles=ArticleCRUD.count(db),
        total_compounds=CompoundCRUD.count(db),
        total_properties=CompoundPropertyCRUD.count(db),
        total_authors=AuthorCRUD.count(db),
    )
