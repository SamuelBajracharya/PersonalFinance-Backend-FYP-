from sqlalchemy.orm import Session
from app.models.goal import Goal, GoalStatus
from app.schemas.goal import GoalCreate
from decimal import Decimal


def create_goal(db: Session, user_id: str, goal: GoalCreate) -> Goal:
    db_goal = Goal(
        user_id=user_id,
        goal_type=goal.goal_type,
        target_amount=goal.target_amount,
        current_amount=Decimal(0),
        deadline=goal.deadline,
        status=GoalStatus.ACTIVE,
    )
    db.add(db_goal)
    db.commit()
    db.refresh(db_goal)
    return db_goal


def get_goals_by_user(db: Session, user_id: str) -> list[Goal]:
    return db.query(Goal).filter(Goal.user_id == user_id).all()


def get_active_goals_by_user(db: Session, user_id: str) -> list[Goal]:
    return (
        db.query(Goal)
        .filter(
            Goal.user_id == user_id,
            Goal.status.notin_([GoalStatus.ACHIEVED, GoalStatus.EXPIRED]),
        )
        .all()
    )


def update_goal(db: Session, goal: Goal) -> Goal:
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal
